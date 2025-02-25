from .. import db
from ..models.wallet import WalletCurrencyType

class ExchangeRate(db.Model):
    __tablename__ = 'exchange_rates'
    
    id = db.Column(db.Integer, primary_key=True)
    base_currency = db.Column(db.Enum(WalletCurrencyType), nullable=False)
    target_currency = db.Column(db.Enum(WalletCurrencyType), nullable=False)
    rate = db.Column(db.Float, nullable=False)
    last_updated = db.Column(db.DateTime, default=db.func.current_timestamp(), onupdate=db.func.current_timestamp(), nullable=False)
    
    __table_args__ = (db.UniqueConstraint("base_currency", "target_currency", name="unique_currency_pair"),)