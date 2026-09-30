import logging
import os
import requests
import time
from datetime import datetime, time as dtime, timedelta, timezone

logger = logging.getLogger(__name__)

# Cap outbound calls so a slow provider can't stall the scheduler job.
REQUEST_TIMEOUT_SECONDS = 15

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

    def reconcile_price_history(self, app, limit=None):
        """Backfill new tickers and correct closes from Massive, within a budget.

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

                