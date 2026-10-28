"""Seed the load-test database and mint a session for every user.

Writes loadtest/users.json: one {token, csrf, wallet_id} per user. Sessions are
minted here with the stack's JWT secret instead of going through /auth/signin,
which is rate limited to 5 a minute per IP and would take hours for thousands of
users. The trade requests k6 sends are otherwise the real thing: the same
cookie, CSRF header, rate limiter and service code a browser would hit.

Wipes and refills the database it points at, so it refuses any database whose
name does not end in _load.

    python loadtest/seed.py [users]
"""
import json
import os
import sys
import time
from decimal import Decimal
from pathlib import Path

from sqlalchemy.engine import make_url

DB_URI = os.getenv("LOADTEST_DB_URI", "postgresql://load:load@localhost:5434/imockmarket_load")
JWT_SECRET = os.getenv("LOADTEST_JWT_SECRET", "loadtest-only-secret-key-that-is-long-enough-for-hs256")
USERS = int(sys.argv[1]) if len(sys.argv) > 1 else 2000
SYMBOLS = [("LT00", "100.00"), ("LT01", "42.50"), ("LT02", "250.00"), ("LT03", "17.25"), ("LT04", "480.00")]
HELD_PER_SYMBOL = 100  # every user holds enough of each symbol to sell from

if not (make_url(DB_URI).database or "").endswith("_load"):
    sys.exit(f"Refusing to seed {DB_URI!r}: the database name must end in _load.")

os.environ.update({
    "SQLALCHEMY_DATABASE_URI": DB_URI,
    "JWT_SECRET_KEY": JWT_SECRET,
    "RUN_BACKGROUND_JOBS": "false",
    "SWAGGER_URL": "/docs",
    "LOG_LEVEL": "WARNING",
})
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from flask_jwt_extended import create_access_token, get_csrf_token  # noqa: E402
from flask_migrate import upgrade  # noqa: E402
from sqlalchemy import insert, select, text  # noqa: E402

from app import create_app, db  # noqa: E402
from app.models.stock_available import AvailableStocks  # noqa: E402
from app.models.stock_price import StockPrice  # noqa: E402
from app.models.user import User, UserRoles  # noqa: E402
from app.models.user_stock_wallet import UserStockWallet  # noqa: E402
from app.models.wallet import Wallet, WalletCurrencyType  # noqa: E402


def main():
    started = time.perf_counter()
    app = create_app()
    with app.app_context():
        upgrade(directory=str(Path(__file__).resolve().parent.parent / "migrations"))
        tables = ", ".join(f'"{t.name}"' for t in db.metadata.sorted_tables)
        db.session.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))

        db.session.execute(insert(AvailableStocks), [
            {"symbol": s, "company_name": f"{s} Inc.", "industry": "Testing", "market_cap": 1_000_000_000,
             "sector": "Technology", "image": "https://example.com/x.png",
             "website": "https://example.com", "description": "Load-test fixture."}
            for s, _ in SYMBOLS
        ])
        db.session.execute(insert(StockPrice), [
            {"symbol": s, "current_price": Decimal(p)} for s, p in SYMBOLS
        ])
        db.session.execute(insert(User), [
            {"first_name": "Load", "last_name": "User", "username": f"load_{n}",
             "email": f"load_{n}@example.com", "password_hash": "x", "is_verified": True,
             "role": UserRoles.USER}
            for n in range(1, USERS + 1)
        ])
        user_ids = [r[0] for r in db.session.execute(select(User.id).order_by(User.id))]
        db.session.execute(insert(Wallet), [
            {"user_id": uid, "balance": Decimal("100000"), "currency": WalletCurrencyType.USD}
            for uid in user_ids
        ])
        db.session.execute(insert(UserStockWallet), [
            {"user_id": uid, "symbol": s, "quantity": HELD_PER_SYMBOL}
            for uid in user_ids for s, _ in SYMBOLS
        ])
        db.session.commit()
        db.session.execute(text("ANALYZE"))
        db.session.commit()

        wallet_by_user = dict(db.session.execute(select(Wallet.user_id, Wallet.id)).all())
        sessions = []
        for uid in user_ids:
            token = create_access_token(identity=str(uid))
            sessions.append({"token": token, "csrf": get_csrf_token(token), "wallet_id": wallet_by_user[uid]})

    out = Path(__file__).resolve().parent / "users.json"
    out.write_text(json.dumps({"symbols": [s for s, _ in SYMBOLS], "users": sessions}))
    print(f"Seeded {USERS} users and {len(SYMBOLS)} symbols in {time.perf_counter() - started:.1f}s -> {out}")


if __name__ == "__main__":
    main()
