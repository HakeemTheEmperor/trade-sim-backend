"""Proves the harness itself: schema, isolation, factories and one real trade."""
import os
from decimal import Decimal

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text

from app import db
from app.models.transactions import Transaction
from app.models.user import User
from app.models.wallet import Wallet
from app.services.stocks_service import StocksService
from tests.conftest import MIGRATIONS_DIR
from tests.factories import make_stock, make_user, make_wallet


def test_health_endpoint(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}


def test_schema_is_at_migration_head():
    config = Config(os.path.join(MIGRATIONS_DIR, "alembic.ini"))
    config.set_main_option("script_location", MIGRATIONS_DIR)
    head = ScriptDirectory.from_config(config).get_current_head()
    current = db.session.execute(text("SELECT version_num FROM alembic_version")).scalar()
    assert current == head


def test_database_is_reset_between_tests_first():
    assert User.query.count() == 0
    assert make_user().id == 1  # identity restarts, so ids are predictable


def test_database_is_reset_between_tests_second():
    # Same assertions as above: whichever runs second must still see an empty DB.
    assert User.query.count() == 0
    assert make_user().id == 1


def test_buy_debits_cost_including_spread():
    user = make_user()
    wallet = make_wallet(user, balance="1000")
    make_stock("TEST", price="100")

    StocksService().buy_stocks(user.id, "TEST", wallet.id, 1)

    # Executes at the ask: 100 * (1 + 0.0005) = 100.05, so the 0.05 is the fee.
    assert db.session.get(Wallet, wallet.id).balance == Decimal("899.9500")
    transaction = Transaction.query.one()
    assert transaction.total_value == Decimal("100.05")
    assert transaction.fee == Decimal("0.05")
