from decimal import Decimal
import time
import json
import threading
import os
from websocket import WebSocketApp
from collections import defaultdict

finnhub_url = os.getenv("FINNHUB_WS_URL")
finnhub_api_key = os.getenv("FINNHUB_API_KEY")

class WebSocketListener:
    def __init__(self, app):
        self.app = app
        self.ws_url = f"{finnhub_url}?token={finnhub_api_key}"
        self.symbols = self.load_symbols()
        self.ws = None
        self.thread = None
        self.running = True
        
        
    def load_symbols(self):
        from .models.stock_available import AvailableStocks
        with self.app.app_context():
            symbols = [avs.symbol for avs in AvailableStocks.query.all()]
            return symbols if symbols else ["AAPL"]
        
    def on_message(self, ws, message):
        data = json.loads(message)
        if data.get("type") == "trade":
            for trade in data["data"]:
                symbol = trade["s"]
                price = trade["p"]
                self.update_stock_price(symbol, price)
    
    def on_error(self, ws, error):
        print(f"WebSocket error: {error}")
        
    def on_close(self, ws, close_status_code, close_msg):
        print(f"WebSocket closed (code: {close_status_code}, msg: {close_msg})")
        if self.running:
            print("Attempting to reconnect")
            time.sleep(4)
            self.start_websocket()
        
    def on_open(self, ws):
        print("### OPEN ###")
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
        print("WebSocket listener started")
            
    
    def stop(self):
        if self.ws:
            self.running = False
            self.ws.close()
            self.thread = None
            print("WebSocket listener stopped")
                
    def update_stock_price(self, symbol, price):
        from . import db
        from .models.stock_price import StockPrice
        with self.app.app_context():
            price_decimal = Decimal(str(price))
            stock = StockPrice.query.filter_by(symbol=symbol).first()
            if stock:
                if stock.current_price > 0:
                    percentage_change = ((price_decimal - stock.current_price) / stock.current_price) * 100
                else:
                    percentage_change = 0
                stock.previous_price = stock.current_price
                stock.current_price = price
                stock.percentage_change = percentage_change
            else:
                stock = StockPrice(symbol=symbol, current_price=price) 
            db.session.add(stock)
            db.session.commit()
            print(f"Updated {symbol} with price {price}")
                