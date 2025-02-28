from ..models.stock_available import AvailableStocks
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