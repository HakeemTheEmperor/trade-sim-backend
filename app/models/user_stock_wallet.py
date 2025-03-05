from .. import db

class UserStockWallet(db.Model):
    __tablename__ = "users_stock_wallet"
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    symbol = db.Column(db.String, db.ForeignKey('available_stocks.symbol'), nullable=False)
    quantity = db.Column(db.Numeric(15, 6), nullable=False, default=0)
    
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=db.func.current_timestamp())
    
    def to_dict(self):
        return {
            'id': self.id,
            'symbol': self.symbol,
            'quantity': self.quantity,
        }
    