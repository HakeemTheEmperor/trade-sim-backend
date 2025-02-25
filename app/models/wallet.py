from .. import db
from enum import Enum

# ISO currency codes for the supported currencies
class WalletCurrencyType(Enum):
    USD = 'USD'
    EUR = 'EUR'

class Wallet(db.Model):
    __tablename__ = 'wallets'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    balance = db.Column(db.Float, default=100000.00, nullable=False)
    currency = db.Column(db.Enum(WalletCurrencyType), default=WalletCurrencyType.USD, nullable=False)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp(), nullable=False)
    updated_at = db.Column(db.DateTime, default=db.func.current_timestamp(), onupdate=db.func.current_timestamp(), nullable=False)
    
    # Fix: Use a string reference for Transaction to avoid circular import
    sent_transactions = db.relationship('Transaction', foreign_keys='[Transaction.from_wallet_id]', backref='sender_wallet', lazy=True)
    received_transactions = db.relationship('Transaction', foreign_keys='[Transaction.to_wallet_id]', backref='receiver_wallet', lazy=True)
    
    def to_dict(self):
        return {
            'id': self.id,
            'balance': self.balance,
            'currency': self.currency.value,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat()
        }