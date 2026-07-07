from .. import db
from ..models.wallet import WalletCurrencyType

class ExchangeRate(db.Model):
    __tablename__ = 'exchange_rates'
    
    id = db.Column(db.Integer, primary_key=True)
    base_currency = db.Column(db.Enum(WalletCurrencyType), nullable=False)
    target_currency = db.Column(db.Enum(WalletCurrencyType), nullable=False)
    rate = db.Column(db.Numeric(18, 8), nullable=False)
    last_updated = db.Column(db.DateTime(timezone=True), default=db.func.now(), onupdate=db.func.now(), nullable=False)
    # When the provider says it will next refresh this rate (time_next_update_unix).
    # We treat a cached rate as fresh until this moment, so we refetch right after
    # the provider updates rather than on a blind clock. Nullable for rows created
    # before this column existed / providers that don't return it.
    next_update = db.Column(db.DateTime(timezone=True), nullable=True)

    
    __table_args__ = (db.UniqueConstraint("base_currency", "target_currency", name="unique_currency_pair"),)