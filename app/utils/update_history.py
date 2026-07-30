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

            today = datetime.today()
            end_date = today - timedelta(days=1)
            start_date = today - timedelta(days=30)

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

                