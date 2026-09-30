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
        self.symbols = self.load_symbols()
        self.ws = None
        self.thread = None
        self.running = True
        self.price_buffer = defaultdict(lambda: None)  # Buffer for latest prices
        self.buffer_lock = threading.Lock()  # Thread-safe buffer access
        self.update_interval = 30  # Seconds between DB updates
        self.start_buffer_thread()  # Start the buffer processing thread

    def load_symbols(self):
        from .models.stock_available import AvailableStocks
        with self.app.app_context():
            symbols = sorted(avs.symbol for avs in AvailableStocks.query.all())
            # Finnhub's free websocket allows ~50 symbols; the rest are covered
            # by PricePoller, which skips whatever this list holds.
            max_symbols = int(os.getenv("FINNHUB_MAX_SYMBOLS", "50"))
            return symbols[:max_symbols] if symbols else ["AAPL"]

    def start_buffer_thread(self):
        self.buffer_thread = threading.Thread(target=self.process_buffer, daemon=True)
        self.buffer_thread.start()

    def process_buffer(self):
        while self.running:
            self.flush_buffer_to_db()
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
        for symbol in self.symbols:
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