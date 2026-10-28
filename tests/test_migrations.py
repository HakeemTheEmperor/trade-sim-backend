"""Migrations that rewrite data are tested against data, not just an empty schema."""
from decimal import Decimal

import pytest
from flask_migrate import downgrade, upgrade
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app import db
from tests.conftest import MIGRATIONS_DIR
from tests.factories import make_stock, make_user

BEFORE_UNIQUE_HOLDINGS = "f3a8d2c61b94"


def holdings(user_id):
    rows = db.session.execute(
        text("SELECT symbol, quantity FROM users_stock_wallet WHERE user_id = :u ORDER BY symbol"),
        {"u": user_id},
    ).all()
    return [(symbol, Decimal(quantity)) for symbol, quantity in rows]


def test_unique_holding_migration_merges_existing_duplicates():
    user = make_user()
    make_stock("AAA", price="10")
    make_stock("BBB", price="10")
    user_id = user.id
    db.session.remove()  # no open transaction may hold a lock the migration needs

    downgrade(directory=MIGRATIONS_DIR, revision=BEFORE_UNIQUE_HOLDINGS)
    try:
        # Without the constraint the same position can exist three times.
        for symbol, quantity in (("AAA", "1.5"), ("AAA", "2"), ("AAA", "0.5"), ("BBB", "7")):
            db.session.execute(
                text("INSERT INTO users_stock_wallet (user_id, symbol, quantity, created_at) "
                     "VALUES (:u, :s, :q, now())"),
                {"u": user_id, "s": symbol, "q": quantity},
            )
        db.session.commit()
        assert len(holdings(user_id)) == 4
        db.session.remove()
    finally:
        upgrade(directory=MIGRATIONS_DIR)

    # Quantities are summed into one row; a position that was not duplicated is untouched.
    assert holdings(user_id) == [("AAA", Decimal("4")), ("BBB", Decimal("7"))]

    # And a duplicate can no longer be created.
    db.session.remove()
    with pytest.raises(IntegrityError, match="uq_users_stock_wallet_user_symbol"):
        db.session.execute(
            text("INSERT INTO users_stock_wallet (user_id, symbol, quantity, created_at) "
                 "VALUES (:u, 'AAA', 1, now())"),
            {"u": user_id},
        )
    db.session.rollback()
