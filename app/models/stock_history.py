from .. import db

class StockHistory(db.Model):
    __tablename__ = 'stock_history'
    
    id = db.Column(db.Integer, primary_key=True)
    symbol = db.Column(db.String(20), nullable=False)
    date = db.Column(db.DateTime(timezone=True), nullable=False)
    cp = db.Column(db.Numeric(10, 4), nullable=False)
    
    __table_args__ = (
        db.UniqueConstraint('symbol', 'date', name='uix_symbol_date'),
    )
    
    def to_dict(self):
        return {
            'id': self.id,
            'symbol': self.symbol,
            'date': self.date,
            'cp': self.cp
        }
    