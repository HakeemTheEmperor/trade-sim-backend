from decimal import Decimal
import logging
import os
import time
import json
import threading
from websocket import WebSocketApp
from collections import defaultdict

from .integrations.providers import Finnhub

logger = logging.getLogger(__name__)

class WebSocketListener:
    def __init__(self, app):
        self.app = app
        self.ws_url = Finnhub.ws_url()
        # The live subscription set. PricePoller holds a reference to this exact
        # object and polls everything outside it, so it is only ever mutated in
        # place (see refresh_hot_set), never rebound.
        self.symbols = set(self.load_symbols())
        self.ws = None
        self.thread = None
        self.running = True
        self.price_buffer = defaultdict(lambda: None)  # Buffer for latest prices
        self.buffer_lock = threading.Lock()  # Thread-safe buffer access
        self.update_interval = 30  # Seconds between DB updates
        self.hot_refresh_interval = int(os.getenv("HOT_SET_REFRESH_SECONDS") or 3600)
        self.start_buffer_thread()  # Start the buffer processing thread

    def load_symbols(self):
        """Pick the symbols worth a live websocket slot: the most-used tickers.

        Finnhub's free websocket allows ~50 symbols; PricePoller covers the rest
        and skips whatever this returns.
        """
        from sqlalchemy import func
        from . import db
        from .models.stock_available import AvailableStocks
        from .models.user_stock_wallet import UserStockWallet
        from .models.watch_list import WatchList

        max_symbols = int(os.getenv("FINNHUB_MAX_SYMBOLS") or 50)
        with self.app.app_context():
            stocks = db.session.query(AvailableStocks.symbol, AvailableStocks.market_cap).all()
            if not stocks:
                return ["AAPL"]

            # Usage = users holding the stock + users watching it.
            usage = {}
            holders = (db.session.query(UserStockWallet.symbol, func.count())
                       .filter(UserStockWallet.quantity > 0)
                       .group_by(UserStockWallet.symbol).all())
            watchers = (db.session.query(WatchList.stock_symbol, func.count())
                        .group_by(WatchList.stock_symbol).all())
            for symbol, n in holders + watchers:
                usage[symbol] = usage.get(symbol, 0) + n

            # Most used first; market cap breaks ties, so an empty app still
            # streams the big names, then alphabetical for a stable order.
            ranked = sorted(stocks, key=lambda s: (-usage.get(s[0], 0), -(s[1] or 0), s[0]))
            return [symbol for symbol, _ in ranked[:max_symbols]]

    def refresh_hot_set(self):
        """Re-rank by current usage and move the websocket subscriptions to match.

        Symbols that drop out are picked up by PricePoller on its next cycle.
        """
        try:
            new = set(self.load_symbols())
        except Exception:
            logger.exception("Hot set refresh failed; keeping current subscriptions")
            return
        add, remove = new - self.symbols, self.symbols - new
        if not add and not remove:
            return

        connected = bool(self.ws and self.ws.sock and self.ws.sock.connected)
        if connected:
            try:
                for symbol in remove:
                    self.ws.send(json.dumps({"type": "unsubscribe", "symbol": symbol}))
                for symbol in add:
                    self.ws.send(json.dumps({"type": "subscribe", "symbol": symbol}))
            except Exception:
                logger.exception("Failed to move websocket subscriptions; will retry next refresh")
                return
        # In place, so the poller's reference stays valid. When not connected,
        # on_open subscribes to whatever this holds.
        self.symbols |= add
        self.symbols -= remove
        logger.info("Hot set changed: +%d -%d (now %d symbols)", len(add), len(remove), len(self.symbols))

    def start_buffer_thread(self):
        self.buffer_thread = threading.Thread(target=self.process_buffer, daemon=True)
        self.buffer_thread.start()

    def process_buffer(self):
        last_refresh = time.monotonic()
        while self.running:
            self.flush_buffer_to_db()
            if time.monotonic() - last_refresh >= self.hot_refresh_interval:
                self.refresh_hot_set()
                last_refresh = time.monotonic()
            time.sleep(self.update_interval)

    def flush_buffer_to_db(self):
        from . import db
        from .utils.price_writer import write_prices

        # Swap the buffer out under the lock and release it straight away, so
        # on_message is never blocked behind DB I/O.
        with self.buffer_lock:
            if not self.price_buffer:
                return  # Nothing to flush
            pending = self.price_buffer
            self.price_buffer = defaultdict(lambda: None)

        logger.debug("Flushing %d buffered prices to db", len(pending))
        with self.app.app_context():
            try:
                write_prices(pending)
                logger.info("Updated %d symbols", len(pending))
            except Exception:
                db.session.rollback()
                logger.exception("Price flush failed; re-queuing %d symbols", len(pending))
                # Put the prices back, but never over a newer tick that arrived
                # while we were writing.
                with self.buffer_lock:
                    for symbol, price_decimal in pending.items():
                        self.price_buffer.setdefault(symbol, price_decimal)

    def on_message(self, ws, message):
        data = json.loads(message)
        if data.get("type") == "trade":
            for trade in data["data"]:
                symbol = trade["s"]
                price = Decimal(str(trade["p"]))  # Convert to Decimal immediately
                with self.buffer_lock:
                    self.price_buffer[symbol] = price  # Buffer the latest price

    def on_error(self, ws, error):
        logger.error("WebSocket error: %s", error)

    def on_close(self, ws, close_status_code, close_msg):
        logger.warning("WebSocket closed (code: %s, msg: %s)", close_status_code, close_msg)
        if self.running:
            time.sleep(30)
            logger.info("Attempting to reconnect")
            self.start_websocket()

    def on_open(self, ws):
        logger.info("WebSocket connection opened")
        for symbol in list(self.symbols):
            ws.send(json.dumps({"type": "subscribe", "symbol": symbol}))

    def start(self):
        if not self.thread:
            self.start_websocket()

    def start_websocket(self):
        self.ws = WebSocketApp(
            self.ws_url,
            on_open=self.on_open,
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close,
        )
        self.thread = threading.Thread(target=self.ws.run_forever, daemon=True)
        self.thread.start()
        logger.info("WebSocket listener started")

    def stop(self):
        if self.ws and self.running:
            self.running = False
            self.ws.close()
            self.thread = None
            self.flush_buffer_to_db()  # Flush any remaining updates
            logger.info("WebSocket listener stopped")