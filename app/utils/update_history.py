import logging
import os
import requests
import time
from datetime import datetime, time as dtime, timedelta, timezone
from decimal import Decimal

from ..integrations.providers import Alpaca

logger = logging.getLogger(__name__)

# Cap outbound calls so a slow provider can't stall the scheduler job.
REQUEST_TIMEOUT_SECONDS = 15

# Symbols per Alpaca bars request; keeps the query string well under URL limits.
ALPACA_CHUNK = 100

HISTORY_DAYS = 30
# A symbol with fewer history rows than this in the window is treated as new
# and gets first call on the reconcile budget.
MIN_HISTORY_ROWS = 10


def market_tz():
    """US market timezone. Massive stamps each daily bar at midnight Eastern,
    so recording closes on the same instant keeps both sources on one row."""
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo("America/New_York")
    except Exception:
        # No tz database on this host (add the `tzdata` package). Fixed EST
        # is an hour off during DST, which can leave a duplicate day row.
        logger.warning("America/New_York tz data unavailable; falling back to UTC-5")
        return timezone(timedelta(hours=-5))


class UpdateHistory:
    def format_date(self,date):
        return date.strftime("%Y-%m-%d")

    def record_daily_closes(self, app):
        """Store today's close for every ticker from the live prices we already hold.

        This is what keeps history current at any ticker count: it reads
        ``stock_price`` (fed by the websocket and the poller) and costs a few
        queries, with no third-party requests. Massive is then only needed to
        backfill and to correct these closes (see reconcile_price_history).
        """
        with app.app_context():
            from .. import db
            from ..models.stock_history import StockHistory
            from ..models.stock_price import StockPrice

            tz = market_tz()
            now = datetime.now(tz)
            # Run before noon Eastern means we're closing out yesterday.
            trade_day = now.date() - timedelta(days=1) if now.hour < 12 else now.date()
            if trade_day.weekday() >= 5:
                logger.info("Skipping daily close for %s: weekend", trade_day)
                return

            day_start = datetime.combine(trade_day, dtime.min, tzinfo=tz)
            day_end = datetime.combine(trade_day + timedelta(days=1), dtime.min, tzinfo=tz)

            # A holiday has no trades, so nothing will have updated that day.
            traded = StockPrice.query.filter(
                StockPrice.updated_at >= day_start, StockPrice.updated_at < day_end
            ).count()
            if traded == 0:
                logger.info("Skipping daily close for %s: no prices updated (market closed?)", trade_day)
                return

            try:
                # Keep rows Massive already wrote: its consolidated close beats
                # our last trade.
                have = {
                    h.symbol for h in
                    StockHistory.query.filter(StockHistory.date == day_start).all()
                }
                added = 0
                for sp in StockPrice.query.all():
                    if sp.symbol in have or sp.current_price <= 0:
                        continue
                    db.session.add(StockHistory(symbol=sp.symbol, date=day_start, cp=sp.current_price))
                    added += 1

                db.session.execute(
                    db.delete(StockHistory).where(
                        StockHistory.date < day_start - timedelta(days=HISTORY_DAYS)
                    )
                )
                db.session.commit()
                logger.info("Recorded daily close for %d symbols (%s)", added, trade_day)
            except Exception:
                db.session.rollback()
                logger.exception("Failed to record daily closes for %s", trade_day)

    def backfill(self, app):
        """Fill a fresh database: every ticker, no budget."""
        if Alpaca.configured():
            self.sync_history_alpaca(app)
        else:
            self.update_price_history(app)

    def reconcile_price_history(self, app):
        """Nightly: backfill new tickers and correct closes from a real provider."""
        if Alpaca.configured():
            self.sync_history_alpaca(app)
        else:
            logger.warning("Alpaca not configured; reconciling history via Massive (rate-limited)")
            self._reconcile_massive(app)

    def sync_history_alpaca(self, app, symbols=None, days=HISTORY_DAYS):
        """Upsert daily bars for every ticker from Alpaca's multi-symbol endpoint.

        One request covers ~100 symbols, so this is O(tickers / 100) and a full
        pass over 1,500 tickers takes minutes, against hours on Massive. It also
        overwrites the closes record_daily_closes wrote with the consolidated
        (SIP) close, which is why both jobs can coexist.
        """
        with app.app_context():
            from .. import db
            from ..models.stock_history import StockHistory
            from ..models.stock_available import AvailableStocks

            if symbols is None:
                symbols = sorted(avs.symbol for avs in AvailableStocks.query.all())
            if not symbols:
                return

            tz = market_tz()
            now = datetime.now(tz)
            start = (now - timedelta(days=days)).date()
            # A daily bar for today is incomplete until the session ends.
            session_over = now.hour > 16 or (now.hour == 16 and now.minute >= 30)

            succeeded, failed = 0, []
            for i in range(0, len(symbols), ALPACA_CHUNK):
                chunk = symbols[i:i + ALPACA_CHUNK]
                try:
                    rows = self._fetch_alpaca_bars(chunk, start, now.date(), session_over)
                    self._upsert_history(rows)
                    succeeded += len(chunk)
                except Exception:
                    db.session.rollback()
                    failed.extend(chunk)
                    logger.exception("Alpaca history sync failed for %d symbols", len(chunk))

            try:
                db.session.execute(db.delete(StockHistory).where(
                    StockHistory.date < datetime.combine(start, dtime.min, tzinfo=tz)
                ))
                db.session.commit()
            except Exception:
                db.session.rollback()
                logger.exception("Failed to prune old price history")

            if failed:
                logger.error("Alpaca history sync: %d succeeded, %d failed (%s)",
                             succeeded, len(failed), ", ".join(failed[:20]))
            else:
                logger.info("Alpaca history sync finished: %d symbols", succeeded)

    def _fetch_alpaca_bars(self, symbols, start, today, session_over):
        """Return ``[{symbol, date, cp}]`` for one chunk, following pagination.

        Results are sorted by symbol then time and the 10,000-point page limit is
        shared across symbols, so a big chunk can span pages.
        """
        params = {
            "symbols": ",".join(symbols),
            "timeframe": "1Day",
            "start": start.isoformat(),
            "adjustment": "split",  # splits would otherwise show as fake price jumps
            "feed": Alpaca.history_feed(),
            "sort": "asc",
            "limit": 10000,
        }
        rows = []
        while True:
            response = requests.get(
                Alpaca.bars_url(), headers=Alpaca.headers(),
                params=params, timeout=REQUEST_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            payload = response.json()
            for symbol, bars in (payload.get("bars") or {}).items():
                for bar in bars:
                    # Bars are stamped at midnight Eastern, in UTC.
                    date = datetime.fromisoformat(bar["t"].replace("Z", "+00:00"))
                    if date.astimezone(market_tz()).date() >= today and not session_over:
                        continue
                    rows.append({"symbol": symbol, "date": date, "cp": Decimal(str(bar["c"]))})
            token = payload.get("next_page_token")
            if not token:
                return rows
            params["page_token"] = token

    def _upsert_history(self, rows):
        from .. import db
        from ..models.stock_history import StockHistory

        if not rows:
            return
        if db.engine.dialect.name == "postgresql":
            from sqlalchemy.dialects.postgresql import insert as pg_insert
            stmt = pg_insert(StockHistory).values(rows)
            stmt = stmt.on_conflict_do_update(
                constraint="uix_symbol_date", set_={"cp": stmt.excluded.cp}
            )
            db.session.execute(stmt)
        else:
            for row in rows:
                existing = StockHistory.query.filter_by(symbol=row["symbol"], date=row["date"]).first()
                if existing:
                    existing.cp = row["cp"]
                else:
                    db.session.add(StockHistory(**row))
        db.session.commit()

    def _reconcile_massive(self, app, limit=None):
        """Massive fallback: backfill new tickers and correct closes, within a budget.

        Massive's free tier is ~5 requests/min, so a full pass is O(tickers).
        Instead, each run covers ``limit`` symbols: tickers with thin history
        first, then a rotating window so every ticker is corrected every
        ``ceil(tickers / limit)`` days.
        """
        limit = limit or int(os.getenv("HISTORY_RECONCILE_PER_RUN") or 100)
        with app.app_context():
            from .. import db
            from ..models.stock_history import StockHistory
            from ..models.stock_available import AvailableStocks

            symbols = sorted(avs.symbol for avs in AvailableStocks.query.all())
            if not symbols:
                return

            cutoff = datetime.now(timezone.utc) - timedelta(days=HISTORY_DAYS)
            counts = dict(
                db.session.query(StockHistory.symbol, db.func.count(StockHistory.id))
                .filter(StockHistory.date >= cutoff)
                .group_by(StockHistory.symbol)
                .all()
            )
            thin = [s for s in symbols if counts.get(s, 0) < MIN_HISTORY_ROWS]
            rest = [s for s in symbols if counts.get(s, 0) >= MIN_HISTORY_ROWS]

            chosen = thin[:limit]
            room = limit - len(chosen)
            if room > 0 and rest:
                start = (datetime.now().toordinal() * limit) % len(rest)
                rotated = rest[start:] + rest[:start]
                chosen += rotated[:room]

        logger.info("Reconciling price history for %d of %d symbols", len(chosen), len(symbols))
        self.update_price_history(app, symbols=chosen)

    def update_price_history(self, app, symbols=None):
        """Pull daily bars from Massive. ``symbols=None`` means every ticker."""
        with app.app_context():
            from .. import db
            from ..models.stock_history import StockHistory
            from ..models.stock_available import AvailableStocks
            from ..integrations.providers import Polygon

            today = datetime.today()
            end_date = today - timedelta(days=1)
            start_date = today - timedelta(days=30)

            if symbols is None:
                symbols = [avs.symbol for avs in AvailableStocks.query.all()]
            start_date_str = self.format_date(start_date)
            end_date_str = self.format_date(end_date)

            succeeded = 0
            failed = []

            # Handled per symbol rather than around the whole loop: a single
            # failure used to abort all ~45 and log one line that read like a
            # transient provider blip, which is how a malformed base URL stayed
            # hidden. Now one bad symbol costs only that symbol, and a total
            # failure is visible as such in the summary below.
            for symbol in symbols:
                try:
                    response = requests.get(
                        Polygon.daily_aggs_url(symbol, start_date_str, end_date_str),
                        timeout=REQUEST_TIMEOUT_SECONDS,
                    )
                    response.raise_for_status()
                    stock_data = response.json().get("results", [])

                    db.session.execute(
                        db.delete(StockHistory).where(
                            (StockHistory.symbol == symbol) & (StockHistory.date < start_date)
                        )
                    )

                    for data in stock_data:
                        date = datetime.fromtimestamp(data["t"] / 1000)

                        existing = StockHistory.query.filter_by(symbol=symbol, date=date).first()
                        if existing:
                            existing.cp = data["c"]
                        else:
                            new_record = StockHistory(
                                symbol=symbol,
                                date=date,
                                cp=data["c"],
                            )
                            db.session.add(new_record)

                    db.session.commit()
                    succeeded += 1
                    logger.info("Successfully updated the price history for %s", symbol)
                except Exception:
                    db.session.rollback()
                    failed.append(symbol)
                    logger.exception("Failed to update price history for %s", symbol)

                # Polygon/Massive free tier allows ~5 requests/minute.
                time.sleep(20)

            if failed:
                logger.error(
                    "Price history update finished: %d succeeded, %d failed (%s)",
                    succeeded, len(failed), ", ".join(failed),
                )
            else:
                logger.info("Price history update finished: %d symbols updated", succeeded)

                