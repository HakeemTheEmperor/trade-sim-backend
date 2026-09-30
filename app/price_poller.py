from decimal import Decimal, InvalidOperation
import logging
import os
import threading

import requests

from .integrations.providers import Alpaca

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT_SECONDS = 15
# Symbols per snapshot request. Keeps the query string well under URL limits.
CHUNK_SIZE = 100
# Pause after a 429 before the next chunk, so we don't hammer a limited key.
RATE_LIMIT_BACKOFF_SECONDS = 30


class PricePoller:
    """Polls Alpaca snapshots for every ticker the Finnhub websocket doesn't cover.

    The websocket is capped at ~50 symbols, so it takes those and this covers the
    rest in a handful of bulk requests per cycle. Prices land in ``stock_price``
    through the same writer the websocket uses.
    """

    def __init__(self, app, exclude_symbols=()):
        self.app = app
        self.exclude_symbols = set(exclude_symbols)
        self.interval = int(os.getenv("PRICE_POLL_INTERVAL_SECONDS", "60"))
        self._stop = threading.Event()
        self.thread = None

    def start(self):
        if not Alpaca.configured():
            logger.warning("ALPACA_API_KEY_ID/ALPACA_API_SECRET_KEY not set; price poller disabled")
            return
        if self.thread:
            return
        self.thread = threading.Thread(target=self._run, name="price-poller", daemon=True)
        self.thread.start()
        logger.info("Price poller started (every %ds, feed=%s)", self.interval, Alpaca.feed())

    def stop(self):
        self._stop.set()

    def _run(self):
        while not self._stop.is_set():
            try:
                self.poll_once()
            except Exception:
                # Never let one bad cycle kill the thread.
                logger.exception("Price poll cycle failed")
            self._stop.wait(self.interval)

    def load_symbols(self):
        from .models.stock_available import AvailableStocks
        with self.app.app_context():
            return sorted(
                avs.symbol for avs in AvailableStocks.query.all()
                if avs.symbol not in self.exclude_symbols
            )

    def poll_once(self):
        from . import db
        from .utils.price_writer import write_prices

        symbols = self.load_symbols()
        if not symbols:
            return

        prices = {}
        for i in range(0, len(symbols), CHUNK_SIZE):
            chunk = symbols[i:i + CHUNK_SIZE]
            try:
                prices.update(self.fetch_chunk(chunk))
            except requests.HTTPError as e:
                status = e.response.status_code if e.response is not None else None
                logger.error("Alpaca snapshot request failed (HTTP %s)", status)
                if status == 429:
                    self._stop.wait(RATE_LIMIT_BACKOFF_SECONDS)
            except requests.RequestException as e:
                logger.error("Alpaca snapshot request failed: %s", e)

        if not prices:
            return

        with self.app.app_context():
            try:
                written = write_prices(prices, skip_unchanged=True)
                logger.info("Poller updated %d of %d symbols", written, len(symbols))
            except Exception:
                db.session.rollback()
                logger.exception("Poller failed to write %d prices", len(prices))

    def fetch_chunk(self, symbols):
        response = requests.get(
            Alpaca.snapshots_url(),
            headers=Alpaca.headers(),
            params={"symbols": ",".join(symbols), "feed": Alpaca.feed()},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        return self.parse_snapshots(response.json())

    @staticmethod
    def parse_snapshots(payload):
        """Turn an Alpaca snapshots response into ``{symbol: Decimal}``.

        Symbols with no trade, or a non-positive price, are skipped.
        """
        prices = {}
        for symbol, snap in (payload or {}).items():
            trade = (snap or {}).get("latestTrade") or {}
            raw = trade.get("p")
            if raw is None:
                continue
            try:
                price = Decimal(str(raw))  # str() first: never Decimal(float)
            except InvalidOperation:
                continue
            if price > 0:
                prices[symbol] = price
        return prices
