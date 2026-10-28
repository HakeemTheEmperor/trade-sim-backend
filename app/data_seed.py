from decimal import Decimal
import logging
import os
import time
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

# Cap outbound calls so a slow provider can't stall the seed job.
REQUEST_TIMEOUT_SECONDS = 15

# The tradable universe. One symbol per line, '#' starts a comment. Growing the
# app to more tickers is an edit to this file, not to code.
TICKERS_FILE = Path(__file__).parent / "data" / "tickers.txt"

# Finnhub's free plan is ~60 calls/min; stay just under it.
FINNHUB_CALL_SPACING_SECONDS = 1.1
FINNHUB_BACKOFF_SECONDS = 60
MARKET_CAP_COMMIT_EVERY = 50


def load_tickers(path=TICKERS_FILE):
    """Read the ticker file: uppercased, de-duplicated, in file order."""
    seen, symbols = set(), []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        symbol = line.split("#", 1)[0].strip().upper()
        if symbol and symbol not in seen:
            seen.add(symbol)
            symbols.append(symbol)
    return symbols


class DataSeed:

    def load_available_stocks(app):
        """Profile tickers from the ticker file that aren't in the database yet.

        Profiles are static, so an existing symbol is never re-fetched: steady
        state costs no FMP calls. FMP's free plan is ~250 calls/day, so each run
        is capped at FMP_DAILY_BUDGET (default 240) new symbols and resumes where
        it stopped on the next run. Each symbol is committed on its own, so one
        bad response (or hitting the limit) never discards the ones already
        loaded.
        """
        with app.app_context():
            from . import db
            from .models.stock_available import AvailableStocks
            from .models.stock_price import StockPrice
            from .integrations.providers import FMP

            budget = int(os.getenv("FMP_DAILY_BUDGET") or 240)
            existing = {row[0] for row in db.session.query(AvailableStocks.symbol).all()}
            missing = [t for t in load_tickers() if t not in existing]
            if not missing:
                logger.info("All %d tickers already profiled", len(existing))
                return

            batch = missing[:budget]
            logger.info("Profiling %d of %d missing tickers", len(batch), len(missing))
            loaded = 0

            for symbol in batch:
                try:
                    response = requests.get(FMP.profile_url(symbol), timeout=REQUEST_TIMEOUT_SECONDS)
                    if response.status_code in (402, 429):
                        logger.warning("FMP limit reached after %d symbols; resuming next run", loaded)
                        break
                    response.raise_for_status()
                    data = response.json()

                    if not data or not isinstance(data, list):
                        logger.warning("No data found for %s", symbol)
                        continue

                    stock_data = data[0]
                    symbol = stock_data.get("symbol") or symbol

                    # /stable renamed this from the legacy /api/v3 name; accept
                    # both so FMP_BASE_URL can point at either.
                    market_cap = stock_data.get("marketCap")
                    if market_cap is None:
                        market_cap = stock_data.get("mktCap")

                    # Every column below is NOT NULL. Price is not required: live
                    # prices come from the websocket and the poller.
                    required = {
                        "company_name": stock_data.get("companyName"),
                        "industry": stock_data.get("industry"),
                        "market_cap": market_cap,
                        "sector": stock_data.get("sector"),
                        "image": stock_data.get("image"),
                        "website": stock_data.get("website"),
                        "description": stock_data.get("description"),
                    }
                    missing_fields = [name for name, value in required.items() if value is None]
                    if missing_fields:
                        logger.warning("Skipping %s, provider omitted: %s", symbol, ", ".join(missing_fields))
                        continue

                    if symbol in existing:
                        continue  # the provider normalised it to a symbol we hold
                    db.session.add(AvailableStocks(symbol=symbol, **required))

                    # Seed a starting price only if nothing has written one; never
                    # overwrite a live price with a stale profile quote.
                    price = stock_data.get("price")
                    if price is not None and not StockPrice.query.filter_by(symbol=symbol).first():
                        db.session.add(StockPrice(symbol=symbol, current_price=Decimal(str(price))))

                    db.session.commit()
                    existing.add(symbol)
                    loaded += 1
                    logger.info("Loaded %s - %s", symbol, required["company_name"])
                except requests.RequestException:
                    db.session.rollback()
                    logger.exception("API error while profiling %s", symbol)
                except Exception:
                    db.session.rollback()
                    logger.exception("Database error while profiling %s", symbol)

            logger.info("Profiled %d new tickers (%d still pending)",
                        loaded, max(len(missing) - loaded, 0))

    def refresh_market_caps(app):
        """Refresh market_cap for every ticker from Finnhub.

        Market cap is the one profile field that drifts, and Finnhub's ~60
        calls/min free plan covers 1,500 tickers in under half an hour, so the
        FMP budget stays reserved for new tickers. Finnhub reports the value in
        millions of USD.
        """
        with app.app_context():
            from . import db
            from .models.stock_available import AvailableStocks
            from .integrations.providers import Finnhub

            if not os.getenv("FINNHUB_API_KEY"):
                logger.warning("FINNHUB_API_KEY not set; skipping market cap refresh")
                return

            limit = int(os.getenv("MARKET_CAP_REFRESH_PER_RUN") or 2000)
            stocks = AvailableStocks.query.order_by(AvailableStocks.symbol).limit(limit).all()
            updated = 0

            for i, stock in enumerate(stocks, start=1):
                try:
                    response = requests.get(
                        Finnhub.profile_url(stock.symbol),
                        headers=Finnhub.headers(),
                        timeout=REQUEST_TIMEOUT_SECONDS,
                    )
                    if response.status_code == 429:
                        logger.warning("Finnhub rate limit hit; pausing %ds", FINNHUB_BACKOFF_SECONDS)
                        time.sleep(FINNHUB_BACKOFF_SECONDS)
                        continue
                    response.raise_for_status()
                    millions = (response.json() or {}).get("marketCapitalization")
                    if millions:
                        stock.market_cap = int(Decimal(str(millions)) * 1_000_000)
                        updated += 1
                except requests.RequestException:
                    logger.exception("Market cap fetch failed for %s", stock.symbol)

                if i % MARKET_CAP_COMMIT_EVERY == 0:
                    db.session.commit()
                time.sleep(FINNHUB_CALL_SPACING_SECONDS)

            try:
                db.session.commit()
            except Exception:
                db.session.rollback()
                logger.exception("Failed to commit market cap refresh")
            logger.info("Refreshed market cap for %d of %d tickers", updated, len(stocks))
