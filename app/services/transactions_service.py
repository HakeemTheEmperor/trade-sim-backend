from datetime import datetime, timezone, timedelta
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError

from ..models.user import User
from ..models.wallet import Wallet, WalletCurrencyType
from ..models.transactions import Transaction, TransactionType, TransactionCategory
from ..models.exchangerate import ExchangeRate
from .. import db

class TransactionsService:
    def get_transaction_history(self, user_id, wallet_id, currency, transaction_category, sort, page, rows):
        # Check for value entered else use default
        sort = sort if sort else 'desc'
        page = page if page else 1
        rows = rows if rows else 10
        
        try:
            if not wallet_id or not user_id:
                raise ValueError("Missing Wallet Id or User's Id")
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
                'transactions': [t.to_dict() for t in paginated_result.items],
                "total": paginated_result.total,
                "page": paginated_result.page,
                "per_page": paginated_result.per_page,
                "pages": paginated_result.pages
            }
        except KeyError:
            raise
        except ValueError:
            raise
        except Exception as e:
            raise RuntimeError(f"An unexpected error occurred: {str(e)}")
        
        
            