"""A trade costs only the database statements it needs.

Each statement is a round trip to Postgres, and on a hosted database a round
trip is milliseconds, so statement count is most of a trade's latency. These
tests pin the count for a buy and a sell sent through the real HTTP stack so a
redundant lookup (a second token check, a re-read after commit, a separate
price query) cannot creep back in unnoticed.

The budgets are ceilings. If a change makes trades cheaper, lower them.
"""
from decimal import Decimal

from flask_jwt_extended import create_access_token, get_csrf_token
from sqlalchemy import event

from app import db
from app.models.user_stock_wallet import UserStockWallet
from tests.factories import make_stock, make_user, make_wallet

BUY_STATEMENT_BUDGET = 8
SELL_STATEMENT_BUDGET = 8


class Statements:
    """Every statement the database receives while the block runs."""

    def __enter__(self):
        self.sent = []
        event.listen(db.engine, "before_cursor_execute", self._record)
        return self

    def __exit__(self, *exc):
        event.remove(db.engine, "before_cursor_execute", self._record)

    def _record(self, conn, cursor, statement, parameters, context, executemany):
        self.sent.append(" ".join(statement.split()))

    def touching(self, table):
        return [s for s in self.sent if f"FROM {table} " in s + " " or f"UPDATE {table} " in s]


def signed_in_client(app, user):
    token = create_access_token(identity=str(user.id))
    client = app.test_client()
    client.set_cookie("access_token_cookie", token)
    return client, {"X-CSRF-TOKEN": get_csrf_token(token)}


def test_buy_stays_within_its_statement_budget(app):
    user = make_user()
    wallet = make_wallet(user, balance="1000")
    make_stock("TEST", price="100")
    user_id, wallet_id = user.id, wallet.id
    client, headers = signed_in_client(app, user)
    db.session.remove()

    with Statements() as statements:
        response = client.post("/api/v1/stocks/buy", headers=headers,
                               json={"symbol": "TEST", "quantity": 1, "wallet_id": wallet_id})

    assert response.status_code == 200
    assert "TEST Inc." in response.get_json()["message"]  # the name still reaches the response
    assert len(statements.sent) <= BUY_STATEMENT_BUDGET, "\n".join(statements.sent)
    # The specific wastes this budget exists to prevent:
    assert len(statements.touching("revoked_tokens")) == 1  # token checked once, not twice
    assert len(statements.touching("available_stocks")) == 1  # not re-read after commit
    assert len(statements.touching("stock_price")) == 0  # price arrives with the stock
    db.session.expire_all()
    assert UserStockWallet.query.filter_by(user_id=user_id).one().quantity == Decimal("1")


def test_sell_stays_within_its_statement_budget(app):
    user = make_user()
    wallet = make_wallet(user, balance="0")
    make_stock("TEST", price="100")
    db.session.add(UserStockWallet(user_id=user.id, symbol="TEST", quantity=5))
    db.session.commit()
    wallet_id = wallet.id
    client, headers = signed_in_client(app, user)
    db.session.remove()

    with Statements() as statements:
        response = client.post("/api/v1/stocks/sell", headers=headers,
                               json={"symbol": "TEST", "quantity": 1, "wallet_id": wallet_id})

    assert response.status_code == 200
    assert "TEST Inc." in response.get_json()["message"]
    assert len(statements.sent) <= SELL_STATEMENT_BUDGET, "\n".join(statements.sent)
    assert len(statements.touching("revoked_tokens")) == 1
    assert len(statements.touching("available_stocks")) == 1
    assert len(statements.touching("stock_price")) == 0
