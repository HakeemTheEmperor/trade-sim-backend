from .. import db

class StockPrice(db.Model):
    __tablename__ = 'stock_price'
    
    id = db.Column(db.Integer, primary_key=True)
    symbol = db.Column(db.String(20), db.ForeignKey('available_stocks.symbol'), unique=True, nullable=False)
    current_price = db.Column(db.Numeric(15, 6), nullable=False)
    previous_price = db.Column(db.Numeric(15, 6), nullable=False, default=0)
    percentage_change = db.Column(db.Numeric(15, 6), nullable=False, default=0)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=db.func.now(), onupdate=db.func.now())

    def to_dict(self):
        return {
            "id": self.id,
            "symbol": self.symbol,
            "current_price": float(self.current_price),  # Convert Decimal to float
            "previous_price": float(self.previous_price),
            "percentage_change": float(self.percentage_change),
            "updated_at": self.updated_at.isoformat()  # Convert datetime to string
        }