from decimal import Decimal
import logging
import os
import requests

logger = logging.getLogger(__name__)

# Cap outbound calls so a slow provider can't stall the seed job.
REQUEST_TIMEOUT_SECONDS = 15

class DataSeed:
    
    def load_available_stocks(app):
        with app.app_context():
            from . import db
            from .models.stock_available import AvailableStocks
            from .models.stock_price import StockPrice
            api_key = os.getenv("FMP_API_KEY")
            base_url = "https://financialmodelingprep.com/api/v3/profile/"
            default_symbols = [
                "AAPL", "NVDA", "MSFT", "AMZN", "GOOG", "META", "TSM", "TSLA", "WMT",
                "JPM", "V", "MA", "ORCL", "UNH", "XOM", "NFLX", "PG", "HD", "KO", "TMUS", "CVX",
                "TM", "PM", "IBM", "MCD", "PEP", "AXP", "DIS", "SHEL", "GS", "ADBE", "CAT", "XIACF",
                "UBER", "SONY", "SHOP", "UL", "TTE", "SBUX", "SPOT", "NKE", "INTC", "UPS", "RACE", "ABNB"
            ]

            try:
                for symbol in default_symbols:
                    url = f"{base_url}{symbol}?apikey={api_key}"
                    response = requests.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
                    response.raise_for_status()
                    data = response.json()

                    if not data:
                        logger.warning("No data found for %s", symbol)
                        continue

                    stock_data = data[0]
                    symbol = stock_data["symbol"]
                    stock = AvailableStocks.query.filter_by(symbol=symbol).first()
                    if stock:
                        stock.company_name = stock_data.get("companyName")
                        stock.sector = stock_data.get("sector")
                        stock.industry = stock_data.get("industry")
                        stock.image = stock_data.get("image")
                        stock.market_cap = stock_data.get("mktCap")
                        stock.description = stock_data.get("description")
                        stock.website = stock_data.get("website")
                    else:
                        stock = AvailableStocks(
                            symbol=symbol,
                            company_name=stock_data.get("companyName"),
                            industry=stock_data.get("industry"),
                            market_cap=stock_data.get("mktCap"),
                            sector=stock_data.get("sector"),
                            image=stock_data.get("image"),
                            website=stock_data.get("website"),
                            description=stock_data.get("description")
                        )
                        db.session.add(stock)
                    logger.info("Loaded %s - %s", symbol, stock_data.get("companyName"))
                    price_decimal = Decimal(str(stock_data.get("price")))
                    
                    stock_price = StockPrice.query.filter_by(symbol=symbol).first()
                    if stock_price:
                        stock_price.previous_price = stock_price.current_price
                        stock_price.current_price = price_decimal
                        if stock_price.previous_price > 0:
                            stock_price.percentage_change = ((stock_price.current_price - stock_price.previous_price)/ stock_price.previous_price) * 100
                        else:
                            stock_price.percentage_change = 0
                    else:
                        stock_price = StockPrice(symbol=symbol, current_price=price_decimal)
                    db.session.add(stock_price)
                # Commit all changes in one go
                db.session.commit()

            except requests.RequestException as e:
                logger.exception("API error while seeding stocks")
                db.session.rollback()
            except Exception as e:
                logger.exception("Database error while seeding stocks")
                db.session.rollback()
                
