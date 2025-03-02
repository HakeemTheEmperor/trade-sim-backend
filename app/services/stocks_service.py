from app.custom_exceptions import DataNotFound
from ..models.stock_available import AvailableStocks
from ..models.stock_price import StockPrice
from ..models.wallet import Wallet

class StocksService:
    def get_available_stocks(self):
        try:
            stocks = AvailableStocks.query.all()
            return [stock.to_dict() for stock in stocks]
        except Exception as e:
            raise RuntimeError(f"An unexpected error occured: {str(e)}")
        
    def get_stocks_by_symbol(self, symbol):
        try:
            stocks = AvailableStocks.query.filter(AvailableStocks.symbol.ilike(f"%{symbol}%")).all()
            return [stock.to_dict() for stock in stocks]
        except Exception as e:
            raise RuntimeError(f"An unexpected error occured: {str(e)}")
        
    def get_stocks_by_company_name(self, name):
        try:
            stocks = AvailableStocks.query.filter(AvailableStocks.company_name.ilike(f"%{name}%")).all()
            return [stock.to_dict() for stock in stocks]
        except Exception as e:
            raise RuntimeError(f"An unexpected error occured: {str(e)}")
        
    def get_stocks_price(self, symbol):
        try:
            stock = StockPrice.query.filter_by(symbol=symbol).first()
            if not stock:
                raise DataNotFound(f"No stock with symbol {symbol} found")
            return stock.to_dict()
        except Exception as e:
            raise RuntimeError(f"An unexpected error occured: {str(e)}")