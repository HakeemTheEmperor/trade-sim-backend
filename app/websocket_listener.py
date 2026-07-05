from decimal import Decimal
import logging
import time
import json
import threading
import os
from websocket import WebSocketApp
from collections import defaultdict

logger = logging.getLogger(__name__)

finnhub_url = os.getenv("FINNHUB_WS_URL", "wss://ws.finnhub.io")  # Default if not set
finnhub_api_key = os.getenv("FINNHUB_API_KEY")

class WebSocketListener:
    def __init__(self, app):
        self.app = app
        self.ws_url = f"{finnhub_url}?token={finnhub_api_key}"
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
            symbols = [avs.symbol for avs in AvailableStocks.query.all()]
            return symbols if symbols else ["AAPL"]

    def start_buffer_thread(self):
        self.buffer_thread = threading.Thread(target=self.process_buffer, daemon=True)
        self.buffer_thread.start()

    def process_buffer(self):
        while self.running:
            self.flush_buffer_to_db()
            time.sleep(self.update_interval)

    def flush_buffer_to_db(self):
        from . import db
        from .models.stock_price import StockPrice
        with self.buffer_lock:
            logger.debug("Flushing price buffer to db")
            if not self.price_buffer:
                return  # Nothing to flush
            with self.app.app_context():
                for symbol, price_decimal in self.price_buffer.items():
                    stock = StockPrice.query.filter_by(symbol=symbol).first()
                    if stock:
                        if stock.current_price > 0:
                            percentage_change = ((price_decimal - stock.current_price) / stock.current_price) * 100
                        else:
                            percentage_change = 0
                        stock.previous_price = stock.current_price
                        stock.current_price = price_decimal  # Use Decimal, not float
                        stock.percentage_change = percentage_change
                    else:
                        stock = StockPrice(symbol=symbol, current_price=price_decimal)
                    db.session.add(stock)
                db.session.commit()
                logger.info("Updated %d symbols", len(self.price_buffer))
                self.price_buffer.clear()  # Clear after commit

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

    def update_stock_price(self, symbol, price):
        # Kept for reference, but not used directly now
        pass