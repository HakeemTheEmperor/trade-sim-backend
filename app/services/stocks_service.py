from decimal import Decimal
from app.custom_exceptions import DataNotFound
from app.models.transactions import Transaction, TransactionCategory, TransactionType
from app.models.user import User
from app.models.user_stock_wallet import UserStockWallet
from ..models.stock_available import AvailableStocks
from ..models.stock_history import StockHistory
from ..models.stock_price import StockPrice
from ..models.wallet import Wallet, WalletCurrencyType
from ..utils.enums_utils import ErrorStatuses
from .. import db

class StocksService:
    def get_available_stocks(self):
        try:
            stocks = AvailableStocks.query.all()
            return [stock.to_short_list() for stock in stocks]
        except Exception as e:
            raise RuntimeError(f"An unexpected error occured: {str(e)}")
        
    def get_stock_by_id(self, id):
        try:
            stock = AvailableStocks.query.get(id)
            if stock:
                return stock.to_dict()
            else:
                raise DataNotFound("Stock not found")
        except DataNotFound:
            raise
        except Exception as e:
            raise RuntimeError(f"An unexpected error occured: {str(e)}")
        
    def search_stocks_by_symbol(self, symbol):
        try:
            stocks = AvailableStocks.query.filter(AvailableStocks.symbol.ilike(f"%{symbol}%")).all()
            return [stock.to_short_list() for stock in stocks]
        except Exception as e:
            raise RuntimeError(f"An unexpected error occured: {str(e)}")
        
    def get_stock_by_exact_symbol(self, symbol):
        try:
            symbol = symbol.upper()
            stock = AvailableStocks.query.filter(AvailableStocks.symbol == symbol).first()
            return stock.to_dict() if stock else None
        except Exception as e:
            raise RuntimeError(f"An unexpected error occurred: {str(e)}")

        
    def get_stocks_by_company_name(self, name):
        try:
            stocks = AvailableStocks.query.filter(AvailableStocks.company_name.ilike(f"%{name}%")).all()
            return [stock.to_short_list() for stock in stocks]
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
            symbol = symbol.upper()
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
                raise ValueError(f"You do not have {quantity} units of {stock.company_name} stock")
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
            user_stocks = (
                db.session.query(UserStockWallet, AvailableStocks)
                .join(AvailableStocks, UserStockWallet.symbol == AvailableStocks.symbol)
                .filter(UserStockWallet.user_id == user_id)
                .all()
                )
            if not user_stocks:
                raise DataNotFound("No stocks found for this user", ErrorStatuses.STOCK_NOT_FOUND.value)
            result = []
            for user_stock, available_stock in user_stocks:
                combined_dict = {
                    'id': user_stock.id,
                    'symbol': user_stock.symbol,
                    'quantity': user_stock.quantity,
                    'company_name': available_stock.company_name,
                    'image': available_stock.image,
                    'price': available_stock.price.to_dict() if available_stock.price else None,
                }
                result.append(combined_dict)
            return result
        except DataNotFound:
            raise
        except Exception as e:
            db.session.rollback()
            raise RuntimeError(f"An unexpected error occurred: {str(e)}")
    
    def get_user_stock_quantity(self, user_id, symbol):
        try:
            symbol = symbol.strip().upper()
            stock = (
                db.session.query(UserStockWallet.quantity)
                .filter(UserStockWallet.user_id == user_id, UserStockWallet.symbol == symbol)
                .first()
            )
            if not stock:
                raise DataNotFound("Stock not found for this user", ErrorStatuses.STOCK_NOT_FOUND.value)
            return float(stock.quantity)
        except DataNotFound:
            raise
        except Exception as e:
            db.session.rollback()
            raise RuntimeError(f"An unexpected error occurred: {str(e)}")
    
    def get_stock_history(self, symbol):
        try:
            stock_history = (
                StockHistory.query
                .filter_by(symbol=symbol)
                .order_by(StockHistory.date.asc())
                .all())
            
            if not stock_history:
                raise DataNotFound("Could not find any price history for this symbol", ErrorStatuses.HISTORY_NOT_FOUND.value)
            return [history.to_dict() for history in stock_history]
        except DataNotFound:
            raise
        except Exception as e:
            db.session.rollback()
            raise RuntimeError(f"An unexpected error occurred: {str(e)}")
        
    def get_user_portfolio(self, user_id):
        try:
            user_stocks = UserStockWallet.query.filter_by(user_id=user_id).all()
            if not user_stocks:
                return {
                "portfolio_value": 0,
                "profit_loss_percentage": 0
                }
            total_cost = 0
            current_value = 0
            
            for stock in user_stocks:
                stock_price = StockPrice.query.filter_by(symbol=stock.symbol).first()
                if not stock_price:
                    continue
                
                current_price = stock_price.current_price
                current_value += stock.quantity * current_price
                
                buy_transactions = Transaction.query.filter_by(
                    user_id=user_id, 
                    stock_symbol=stock.symbol,
                    transaction_type=TransactionType.BUY
                ).all()
                
                sell_transactions = Transaction.query.filter_by(
                    user_id=user_id, 
                    stock_symbol=stock.symbol,
                    transaction_type=TransactionType.SELL
                ).all()
                
                
                total_bought = sum(tx.quantity for tx in buy_transactions)
                total_sold = sum(tx.quantity for tx in sell_transactions)
                net_quantity = total_bought - total_sold
                
                if net_quantity > 0:
                    total_buy_cost = sum(tx.quantity * tx.price_per_share for tx in buy_transactions)
                    avg_buy_price = total_buy_cost / total_bought 
                    total_cost += avg_buy_price * net_quantity
            if total_cost == 0:
                profit_loss_percentage = 0
            else:
                print("Got here")
                print(type(current_value))
                print(type(total_cost))
                profit_loss_percentage = ((current_value - Decimal(total_cost)) / Decimal(total_cost)) * 100
                
            return {
                "portfolio_value": current_value,
                "profit_loss_percentage": profit_loss_percentage
            }
        except Exception as e:
            print(e)
            db.session.rollback()
            raise RuntimeError(f"An unexpected error occured: {str(e)}")