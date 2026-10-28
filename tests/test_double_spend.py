"""Concurrent trades against one wallet or one position must never overspend.

The protection under test is the row lock taken with ``with_for_update()`` in
StocksService.buy_stocks / sell_stock. Every order is released at the same
instant by a barrier, so the threads genuinely race.

How much of that race reaches Postgres at once is bounded by the app's
SQLAlchemy connection pool (the same bound production has), so "500 concurrent
orders" means 500 simultaneous requests with the pool as the funnel, not 500
simultaneous database sessions.
"""
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

from flask_jwt_extended import create_access_token, get_csrf_token

from app import db
from app.models.transactions import Transaction, TransactionType
from app.models.user_stock_wallet import UserStockWallet
from app.models.wallet import Wallet
from app.services.stocks_service import StocksService
from tests.factories import make_stock, make_user, make_wallet

ORDERS = 500
AFFORDABLE_BUYS = 10
# One share at 100 executes at 100 * 1.0005 = 100.05, so this balance buys
# exactly ten shares and leaves exactly zero. An eleventh would overdraw it.
BALANCE = Decimal("1000.50")
COST_PER_BUY = Decimal("100.05")


def run_concurrently(app, count, task):
    """Run ``task(i)`` on ``count`` threads released together; return the results."""
    barrier = threading.Barrier(count, timeout=120)

    def worker(i):
        with app.app_context():
            try:
                barrier.wait()
                return task(i)
            finally:
                db.session.remove()

    with ThreadPoolExecutor(max_workers=count) as pool:
        return list(pool.map(worker, range(count)))


def classify(call, rejection):
    """'ok', 'rejected' (the expected business refusal), or a description of a failure."""
    try:
        call()
        return "ok"
    except ValueError as e:
        return "rejected" if rejection in str(e) else f"error: {e}"
    except Exception as e:  # anything else is a real failure, never a refusal
        return f"error: {type(e).__name__}: {e}"


def report(capsys, line):
    with capsys.disabled():
        print(f"\n  RESULT: {line}")


def test_concurrent_buys_cannot_overdraw_wallet(app, capsys):
    user = make_user()
    wallet = make_wallet(user, balance=BALANCE)
    make_stock("TEST", price="100")
    user_id, wallet_id = user.id, wallet.id

    results = run_concurrently(
        app, ORDERS,
        lambda i: classify(
            lambda: StocksService().buy_stocks(user_id, "TEST", wallet_id, 1),
            rejection="Insufficient balance",
        ),
    )

    failures = [r for r in results if r not in ("ok", "rejected")]
    assert not failures, f"{len(failures)} orders failed unexpectedly, e.g. {failures[:3]}"
    outcomes = Counter(results)
    assert outcomes["ok"] == AFFORDABLE_BUYS
    assert outcomes["rejected"] == ORDERS - AFFORDABLE_BUYS

    db.session.expire_all()
    final = db.session.get(Wallet, wallet_id).balance
    assert final == Decimal("0")

    buys = Transaction.query.filter_by(transaction_type=TransactionType.BUY).all()
    assert len(buys) == AFFORDABLE_BUYS
    # Money is conserved: what left the wallet is exactly what the ledger records.
    assert BALANCE - final == sum(t.total_value for t in buys) == AFFORDABLE_BUYS * COST_PER_BUY

    holdings = UserStockWallet.query.filter_by(user_id=user_id).all()
    assert len(holdings) == 1 and holdings[0].quantity == AFFORDABLE_BUYS

    overdrafts = max(0, outcomes["ok"] - AFFORDABLE_BUYS) + (1 if final < 0 else 0)
    report(capsys, f"{ORDERS} concurrent orders, {overdrafts} overdrafts")
    assert overdrafts == 0


def test_concurrent_sells_cannot_oversell_a_position(app, capsys):
    held = 10
    sells = 200
    user = make_user()
    wallet = make_wallet(user, balance="0")
    make_stock("TEST", price="100")
    db.session.add(UserStockWallet(user_id=user.id, symbol="TEST", quantity=held))
    db.session.commit()
    user_id, wallet_id = user.id, wallet.id

    results = run_concurrently(
        app, sells,
        lambda i: classify(
            lambda: StocksService().sell_stock(user_id, "TEST", wallet_id, 1),
            rejection="You do not have",
        ),
    )

    failures = [r for r in results if r not in ("ok", "rejected")]
    assert not failures, f"{len(failures)} orders failed unexpectedly, e.g. {failures[:3]}"
    outcomes = Counter(results)
    assert outcomes["ok"] == held
    assert outcomes["rejected"] == sells - held

    db.session.expire_all()
    # Sold at the bid: 100 * (1 - 0.0005) = 99.95 a share.
    assert db.session.get(Wallet, wallet_id).balance == held * Decimal("99.95")
    assert UserStockWallet.query.filter_by(user_id=user_id).count() == 0  # emptied, row removed

    report(capsys, f"{sells} concurrent sells of a {held}-share position, "
                   f"{max(0, outcomes['ok'] - held)} oversold")


def test_concurrent_buys_over_http(app, capsys):
    # The buy route is limited to 30 requests a minute per user, so 30 is the
    # most one user can fire at the full stack (JWT cookie, CSRF, rate limiter,
    # error handlers, service) at once. More would test the limiter, not the lock.
    requests_per_user = 30
    user = make_user()
    wallet = make_wallet(user, balance=BALANCE)
    make_stock("TEST", price="100")
    user_id, wallet_id = user.id, wallet.id
    token = create_access_token(identity=str(user_id))
    csrf = get_csrf_token(token)

    def buy(i):
        client = app.test_client()
        client.set_cookie("access_token_cookie", token)
        response = client.post(
            "/api/v1/stocks/buy",
            json={"symbol": "TEST", "quantity": 1, "wallet_id": wallet_id},
            headers={"X-CSRF-TOKEN": csrf},
        )
        if response.status_code == 200:
            return "ok"
        if response.status_code == 400 and "Insufficient balance" in response.get_json()["message"]:
            return "rejected"
        return f"error: {response.status_code} {response.get_data(as_text=True)[:100]}"

    results = run_concurrently(app, requests_per_user, buy)

    failures = [r for r in results if r not in ("ok", "rejected")]
    assert not failures, f"{len(failures)} requests failed unexpectedly, e.g. {failures[:3]}"
    outcomes = Counter(results)
    assert outcomes["ok"] == AFFORDABLE_BUYS
    assert outcomes["rejected"] == requests_per_user - AFFORDABLE_BUYS

    db.session.expire_all()
    assert db.session.get(Wallet, wallet_id).balance == Decimal("0")
    report(capsys, f"{requests_per_user} concurrent HTTP buys, "
                   f"{max(0, outcomes['ok'] - AFFORDABLE_BUYS)} overdrafts")
