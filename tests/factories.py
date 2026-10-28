"""Small builders for test data. Each commits, so other threads can see the rows."""
import uuid
from decimal import Decimal

from app import db
from app.models.stock_available import AvailableStocks
from app.models.stock_price import StockPrice
from app.models.user import User
from app.models.wallet import Wallet, WalletCurrencyType

TEST_PASSWORD = "password123"


def make_user(**overrides):
    suffix = uuid.uuid4().hex[:10]
    fields = {
        "first_name": "Test",
        "last_name": "User",
        "username": f"user_{suffix}",
        "email": f"user_{suffix}@example.com",
        "is_verified": True,
    }
    fields.update(overrides)
    user = User(**fields)
    user.set_password(TEST_PASSWORD)
    db.session.add(user)
    db.session.commit()
    return user


def make_wallet(user, balance="100000", currency=WalletCurrencyType.USD):
    wallet = Wallet(user_id=user.id, balance=Decimal(str(balance)), currency=currency)
    db.session.add(wallet)
    db.session.commit()
    return wallet


def make_stock(symbol="TEST", price="100"):
    db.session.add(AvailableStocks(
        symbol=symbol,
        company_name=f"{symbol} Inc.",
        industry="Testing",
        market_cap=1_000_000_000,
        sector="Technology",
        image="https://example.com/logo.png",
        website="https://example.com",
        description="A fixture company.",
    ))
    db.session.flush()  # stock_price.symbol is a foreign key to this row
    db.session.add(StockPrice(symbol=symbol, current_price=Decimal(str(price))))
    db.session.commit()
    return AvailableStocks.query.filter_by(symbol=symbol).one()
