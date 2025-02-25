from .. import db
from enum import Enum
from sqlalchemy.orm import validates
from ..models.wallet import WalletCurrencyType


class TransactionCategory(Enum):
    STOCK_TRADE = "STOCK_TRADE"
    WALLET_TRANSFER = "WALLET_TRANSFER"
    DEPOSIT = "DEPOSIT"
    WITHDRAWAL = "WITHDRAWAL"
    
class TransactionType(Enum):
    BUY = "BUY"
    SELL = "SELL"
    DEBIT = "DEBIT"
    CREDIT = "CREDIT"
    
class Transaction(db.Model):
    __tablename__ = 'transactions'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    from_wallet_id = db.Column(db.Integer, db.ForeignKey('wallets.id'), nullable=True)  # Sender Wallet
    to_wallet_id = db.Column(db.Integer, db.ForeignKey('wallets.id'), nullable=True)  # Receiver Wallet
    
    stock_symbol = db.Column(db.String(10), nullable=True) 
    transaction_type = db.Column(db.Enum(TransactionType), nullable=False)
    transaction_category = db.Column(db.Enum(TransactionCategory), nullable=False)

    quantity = db.Column(db.Integer, nullable=True)
    price_per_share = db.Column(db.Float, nullable=True)
    total_value = db.Column(db.Float, nullable=False)
    currency = db.Column(db.Enum(WalletCurrencyType), nullable=False)
    timestamp = db.Column(db.DateTime, default=db.func.current_timestamp(), nullable=False)

    # Validation to update total value for stock transactions
    @validates("quantity", "price_per_share")
    def update_total_value(self, key, value):
        setattr(self, key, value)
        if self.quantity and self.price_per_share:
            self.total_value = self.quantity * self.price_per_share
        return value

