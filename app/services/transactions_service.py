from sqlalchemy import or_
from app.models.stock_available import AvailableStocks

from ..models.user import User
from ..models.wallet import Wallet, WalletCurrencyType
from ..models.transactions import Transaction, TransactionCategory
from .. import db
from ..custom_exceptions import DataNotFound, MissingProperties
from ..utils.validation_utils import clamp_pagination

class TransactionsService:
    def get_transaction_history(self, user_id, wallet_id, currency, transaction_category, sort, page, rows):
        # Check for value entered else use default; cap page size to avoid unbounded queries
        page, rows = clamp_pagination(page, rows)
        sort = sort.lower() if isinstance(sort, str) else 'asc'
        
        try:
            if not wallet_id or not user_id:
                raise MissingProperties("Missing Wallet's Id or User's Id")
            query = Transaction.query
            query = query.filter(Transaction.user_id == user_id)
            query = query.filter(or_(Transaction.from_wallet_id == wallet_id, Transaction.to_wallet_id == wallet_id))
            if currency:
                currency = WalletCurrencyType[currency]                
                query = query.filter(Transaction.currency == currency)
            if transaction_category:
                transaction_category = TransactionCategory[transaction_category]                
                query = query.filter(Transaction.transaction_category == transaction_category)
                
            if sort == 'asc':
                query = query.order_by(Transaction.timestamp.asc())
            else:
                query = query.order_by(Transaction.timestamp.desc())
            
            # Pagination
            paginated_result = query.paginate(page=page, per_page=rows, error_out=False)
            
            return {
                "message": "Transaction history gotten successfully",
                "data": {
                'transactions': [t.to_dict() for t in paginated_result.items],
                "total": paginated_result.total,
                "page": paginated_result.page,
                "per_page": paginated_result.per_page,
                "pages": paginated_result.pages
                }
            }
        except MissingProperties:
            raise
        except KeyError:
            raise
        except ValueError:
            raise
        except Exception as e:
            raise RuntimeError(f"An unexpected error occurred: {str(e)}")
        
    def get_transaction_details(self, transaction_id, user_id):
        try:
            from_wallet = db.aliased(Wallet, name="from_wallet")
            to_wallet = db.aliased(Wallet, name="to_wallet")
            from_user = db.aliased(User, name="from_user")
            to_user = db.aliased(User, name="to_user")
            stock = db.aliased(AvailableStocks, name="stock")

            transaction = (
                db.session.query(
                    Transaction,
                    from_user.first_name.label("from_user"),
                    from_user.last_name.label("from_last_name"),
                    from_wallet.currency.label("from_wallet_currency"),
                    to_user.first_name.label("to_user"),
                    to_user.last_name.label("to_last_name"),
                    to_wallet.currency.label("to_wallet_currency"),
                    stock.image.label("stock_image")
                )
                .outerjoin(from_wallet, from_wallet.id == Transaction.from_wallet_id)
                .outerjoin(from_user, from_user.id == from_wallet.user_id)
                .outerjoin(to_wallet, to_wallet.id == Transaction.to_wallet_id)
                .outerjoin(to_user, to_user.id == to_wallet.user_id)
                .outerjoin(stock, stock.symbol == Transaction.stock_symbol)
                .filter(Transaction.id == transaction_id, Transaction.user_id == user_id)
                .first()
            )
            if not transaction:
                raise DataNotFound("No transaction with that id found")
            txn, from_user, from_last_name, from_wallet_currency, to_user, to_last_name, to_wallet_currency, stock_image = transaction

            return {
                "id": txn.id,
                "user_id": txn.user_id,
                "from_wallet_id": txn.from_wallet_id,
                "from_username": f"{from_user} {from_last_name} {from_wallet_currency.value}" if from_user else None,
                "to_wallet_id": txn.to_wallet_id,
                "to_username": f"{to_user} {to_last_name} {to_wallet_currency.value}" if to_user else None,
                "transaction_type": txn.transaction_type.name,
                "transaction_category": txn.transaction_category.name,
                "total_value": txn.total_value,
                "currency": txn.currency.name,
                "timestamp": txn.timestamp.isoformat(),
                "stockSymbol": txn.stock_symbol,
                "quantity": txn.quantity,
                "pps": txn.price_per_share,
                "stockImage": stock_image
            }
        except DataNotFound:
            raise
        except ValueError:
            raise
        except Exception as e:
            db.session.rollback()
            raise RuntimeError(f"An unexpected error occurred: {str(e)}")
            