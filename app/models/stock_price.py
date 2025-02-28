from .. import db

class StockPrice(db.Model):
    __tablename__ = 'stock_price'
    
    id = db.Column(db.Integer, primary_key=True)
    symbol = db.Column(db.String(20), unique=True, nullable=False)
    current_price = db.Column(db.Numeric(15, 6), nullable=False)
    previous_price = db.Column(db.Numeric(15, 6), nullable=False, default=0)
    percentage_change = db.Column(db.Numeric(15, 6), nullable=False, default=0)  # Store percentage change 
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=db.func.now(), onupdate=db.func.now())

    