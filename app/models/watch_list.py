from .. import db

class WatchList(db.Model):
    __tablename__ = "watchlists"
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    stock_symbol = db.Column(db.String, db.ForeignKey("available_stocks.symbol"), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=db.func.now(), nullable=False)
    
    user = db.relationship("User", backref="watchlist")
    stock = db.relationship("AvailableStocks", backref="watchlist")    