from .. import db

class UserStockWallet(db.Model):
    __tablename__ = "users_stock_wallet"
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    symbol = db.Column(db.String, db.ForeignKey('available_stocks.symbol'), nullable=False)
    quantity = db.Column(db.Numeric(15, 6), nullable=False, default=0)
    
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=db.func.current_timestamp())

    # One row per position. Trades add to it with INSERT ... ON CONFLICT, which
    # needs this constraint, and it stops concurrent first buys creating two rows
    # for the same holding. Its index leads with user_id, so it also serves "all
    # holdings for these users" and the (user_id, symbol) lookups.
    __table_args__ = (
        db.UniqueConstraint("user_id", "symbol", name="uq_users_stock_wallet_user_symbol"),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'symbol': self.symbol,
            'quantity': self.quantity,
        }
    