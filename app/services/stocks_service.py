from app.custom_exceptions import DataNotFound
from app.models.transactions import Transaction, TransactionCategory, TransactionType
from app.models.user import User
from app.models.user_stock_wallet import UserStockWallet
from ..models.stock_available import AvailableStocks
from ..models.stock_price import StockPrice
from ..models.wallet import Wallet, WalletCurrencyType
from ..utils.enums_utils import ErrorStatuses
from .. import db

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
                raise DataNotFound(f"No stock with symbol {symbol} found", ErrorStatuses.STOCK_NOT_FOUND.value)
            return stock.to_dict()
        except Exception as e:
            raise RuntimeError(f"An unexpected error occured: {str(e)}")
        
    def buy_stocks(self, user_id, symbol, wallet_id, quantity):
        try:
            stock = AvailableStocks.query.filter_by(symbol=symbol).first()
            if not stock:
                raise DataNotFound("We could not find any stock with that symbol. Confirm symbol and try again", ErrorStatuses.STOCK_NOT_FOUND.value)
            stock_price = StockPrice.query.filter_by(symbol=symbol).first()
            if not stock_price:
                raise DataNotFound(f"No price data available for {symbol}", ErrorStatuses.PRICE_NOT_FOUND.value)
            current_price = stock_price.current_price
            total_cost = current_price * quantity
            total_cost = float(total_cost)
            
            wallet = Wallet.query.filter_by(user_id=user_id, id=wallet_id).first()
            if not wallet:
                raise DataNotFound("We did not find the specified wallet for this user", ErrorStatuses.WALLET_NOT_FOUND.value)
            if wallet.balance < total_cost:
                raise ValueError("Insufficient balance.")
            wallet.balance -= total_cost
            
            stock_wallet = UserStockWallet.query.filter_by(user_id=user_id, symbol=symbol).first()
            if stock_wallet:
                stock_wallet.quantity += quantity
            else:
                stock_wallet = UserStockWallet(user_id=user_id, symbol=symbol, quantity=quantity)
            
            transaction_log = Transaction(
                user_id=user_id,
                from_wallet_id=wallet_id,
                stock_symbol=symbol,
                quantity=quantity,
                price_per_share=current_price,
                transaction_type=TransactionType.BUY,
                transaction_category=TransactionCategory.STOCK_TRADE,
                currency=wallet.currency,
                total_value=total_cost
            )
            db.session.add(transaction_log)
            db.session.add(stock_wallet)
            db.session.commit()
            return {"message": f"You have successfully PURCHASED {quantity} unit of {stock.company_name} stocks for {quantity * current_price}"}
        except DataNotFound:
            raise
        except ValueError:
            raise
        except Exception as e:
            db.session.rollback()
            raise RuntimeError(f"An unexpected error occurred: {str(e)}")
            
    def sell_stock(self, user_id, symbol, wallet_id, quantity):
        try:
            stock = AvailableStocks.query.filter_by(symbol=symbol).first()
            if not stock:
                raise DataNotFound("We could not find any stock with that symbol. Confirm symbol and try again", ErrorStatuses.STOCK_NOT_FOUND.value)
            stock_wallet = UserStockWallet.query.filter_by(user_id=user_id, symbol=symbol).first()
            if not stock_wallet or stock_wallet.quantity < quantity:
                raise ValueError(f"You do not have {quantity} of {stock.company_name} stock")
            stock_price = StockPrice.query.filter_by(symbol=symbol).first()
            if not stock_price:
                raise DataNotFound(f"No price data available for {symbol}", ErrorStatuses.PRICE_NOT_FOUND.value)
            current_price = stock_price.current_price
            total_cost = float(quantity * current_price)
            
            wallet = Wallet.query.filter_by(user_id=user_id, id=wallet_id).first()
            if not wallet or wallet.currency != WalletCurrencyType.USD:
                raise DataNotFound("We did not find a USD wallet for this user", ErrorStatuses.WALLET_NOT_FOUND.value)
            wallet.balance += total_cost
            stock_wallet.quantity -= quantity
            
            transaction_log = Transaction(
                user_id=user_id,
                from_wallet_id=wallet_id,
                stock_symbol=symbol,
                quantity=quantity,
                price_per_share=current_price,
                transaction_type=TransactionType.SELL,
                transaction_category=TransactionCategory.STOCK_TRADE,
                currency=wallet.currency,
                total_value=total_cost
            )
            db.session.add(transaction_log)
            db.session.commit()
            return {"message": f"You have successfully SOLD {quantity} unit of {stock.company_name} stocks for {total_cost}"}
        except DataNotFound:
            raise
        except ValueError:
            raise
        except Exception as e:
            db.session.rollback()
            raise RuntimeError(f"An unexpected error occurred: {str(e)}")
            
    def get_all_user_stocks(self, user_id):
        try:
            user_stocks = UserStockWallet.query.filter_by(user_id=user_id).all()
            if not user_stocks:
                raise DataNotFound("No stocks found for this user", ErrorStatuses.STOCK_NOT_FOUND.value)
            return [stock.to_dict() for stock in user_stocks]
        except DataNotFound:
            raise
        except Exception as e:
            db.session.rollback()
            raise RuntimeError(f"An unexpected error occurred: {str(e)}")
                