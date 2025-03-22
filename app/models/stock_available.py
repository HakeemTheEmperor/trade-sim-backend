from .. import db

class AvailableStocks(db.Model):
    __tablename__ = 'available_stocks'
    id = db.Column(db.Integer, primary_key=True)
    symbol = db.Column(db.String(20), unique=True, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=db.func.now(), nullable=False)
    company_name = db.Column(db.String(100), nullable=False)
    industry = db.Column(db.String(50), nullable=False)
    market_cap = db.Column(db.BigInteger, nullable=False)
    sector = db.Column(db.String(50), nullable=False)
    image = db.Column(db.String(255), nullable=False)
    website = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=False)
    
    
    # Relationship to StockPrice
    price = db.relationship('StockPrice', backref='available_stock', uselist=False, lazy='joined')
    
    def to_short_list(self):
        return {
            'id': self.id,
            'symbol': self.symbol,
            'company_name': self.company_name,
            'image': self.image,
            'price': self.price.to_dict(),
        }

    def to_dict(self, include_price=True):
        return {
            'id': self.id,
            'symbol': self.symbol,
            'company_name': self.company_name,
            'industry': self.industry,
            'market_cap': self.market_cap,
            'sector': self.sector,
            'image': self.image,
            'price': self.price.to_dict() if self.price and include_price else None,  # Handle None case
            'website': self.website,
            'description': self.description
        }