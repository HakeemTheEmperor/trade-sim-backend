import logging
import requests
import time
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Cap outbound calls so a slow provider can't stall the scheduler job.
REQUEST_TIMEOUT_SECONDS = 15

class UpdateHistory:
    def format_date(self,date):
        return date.strftime("%Y-%m-%d")
    
    def update_price_history(self, app):
        with app.app_context():
            from .. import db
            from ..models.stock_history import StockHistory
            from ..models.stock_available import AvailableStocks
            from ..integrations.providers import Polygon

            try:
                today = datetime.today()
                end_date = today - timedelta(days=1)
                start_date = today - timedelta(days=30)
                
                symbols = [avs.symbol for avs in AvailableStocks.query.all()]
                start_date_str = self.format_date(start_date)
                end_date_str = self.format_date(end_date)
                
                for symbol in symbols:
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
                    logger.info("Successfully updated the price history for %s", symbol)
                    time.sleep(20)
            except Exception as e:
                logger.exception("Failed to update price history")
                
                