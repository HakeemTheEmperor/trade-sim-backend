"""What a buy and a sell do, including every way they can be refused.

The refusals matter as much as the successes: each one has to leave the wallet,
the holding and the ledger exactly as it found them.
"""
from decimal import Decimal

import pytest

from app import db
from app.custom_exceptions import DataNotFound
from app.models.transactions import Transaction, TransactionType
from app.models.user_stock_wallet import UserStockWallet
from app.models.wallet import Wallet, WalletCurrencyType
from app.services.stocks_service import StocksService
from tests.factories import make_stock, make_user, make_wallet


def balance(wallet_id):
    db.session.expire_all()
    return db.session.get(Wallet, wallet_id).balance


def holding(user_id, symbol="TEST"):
    db.session.expire_all()
    row = UserStockWallet.query.filter_by(user_id=user_id, symbol=symbol).first()
    return row.quantity if row else None


def test_buy_opens_a_position_then_adds_to_it():
    user = make_user()
    wallet = make_wallet(user, balance="1000")
    make_stock("TEST", price="10")
    service = StocksService()

    service.buy_stocks(user.id, "TEST", wallet.id, 2)
    service.buy_stocks(user.id, "TEST", wallet.id, "3.5")

    assert holding(user.id) == Decimal("5.5")
    assert UserStockWallet.query.filter_by(user_id=user.id).count() == 1
    assert Transaction.query.filter_by(transaction_type=TransactionType.BUY).count() == 2
    # 5.5 shares at 10 * 1.0005 = 10.005 each
    assert balance(wallet.id) == Decimal("1000") - Decimal("55.0275")


def test_buy_records_the_wallets_currency():
    user = make_user()
    wallet = make_wallet(user, balance="1000")
    make_stock("TEST", price="10")

    StocksService().buy_stocks(user.id, "TEST", wallet.id, 1)

    assert Transaction.query.one().currency == WalletCurrencyType.USD


def test_buy_without_enough_money_changes_nothing():
    user = make_user()
    wallet = make_wallet(user, balance="50")
    make_stock("TEST", price="100")

    with pytest.raises(ValueError, match="Insufficient balance"):
        StocksService().buy_stocks(user.id, "TEST", wallet.id, 1)

    assert balance(wallet.id) == Decimal("50")
    assert holding(user.id) is None
    assert Transaction.query.count() == 0


def test_buy_that_the_spread_makes_unaffordable_is_refused():
    # 100 shares at 10 costs 1000 at the quote but 1000.50 at the ask.
    user = make_user()
    wallet = make_wallet(user, balance="1000")
    make_stock("TEST", price="10")

    with pytest.raises(ValueError, match="Insufficient balance"):
        StocksService().buy_stocks(user.id, "TEST", wallet.id, 100)

    assert balance(wallet.id) == Decimal("1000")


def test_buy_with_someone_elses_wallet_is_refused():
    owner, intruder = make_user(), make_user()
    wallet = make_wallet(owner, balance="1000")
    make_stock("TEST", price="10")

    with pytest.raises(DataNotFound):
        StocksService().buy_stocks(intruder.id, "TEST", wallet.id, 1)

    assert balance(wallet.id) == Decimal("1000")
    assert holding(intruder.id) is None


def test_buy_of_an_unknown_symbol_or_without_a_price_is_refused():
    user = make_user()
    wallet = make_wallet(user, balance="1000")

    with pytest.raises(DataNotFound):
        StocksService().buy_stocks(user.id, "NOPE", wallet.id, 1)

    assert balance(wallet.id) == Decimal("1000")


def test_sell_reduces_the_position_and_pays_the_bid():
    user = make_user()
    wallet = make_wallet(user, balance="0")
    make_stock("TEST", price="100")
    db.session.add(UserStockWallet(user_id=user.id, symbol="TEST", quantity=5))
    db.session.commit()

    StocksService().sell_stock(user.id, "TEST", wallet.id, 2)

    assert holding(user.id) == Decimal("3")
    assert balance(wallet.id) == Decimal("199.9")  # 2 * 100 * 0.9995
    assert Transaction.query.filter_by(transaction_type=TransactionType.SELL).one().fee == Decimal("0.1")


def test_selling_the_whole_position_removes_the_row():
    user = make_user()
    wallet = make_wallet(user, balance="0")
    make_stock("TEST", price="100")
    db.session.add(UserStockWallet(user_id=user.id, symbol="TEST", quantity=5))
    db.session.commit()

    StocksService().sell_stock(user.id, "TEST", wallet.id, 5)

    assert holding(user.id) is None


def test_selling_more_than_held_changes_nothing():
    user = make_user()
    wallet = make_wallet(user, balance="0")
    make_stock("TEST", price="100")
    db.session.add(UserStockWallet(user_id=user.id, symbol="TEST", quantity=5))
    db.session.commit()

    with pytest.raises(ValueError, match="You do not have"):
        StocksService().sell_stock(user.id, "TEST", wallet.id, 6)

    # The wallet is credited before the holding is checked, so this proves the
    # credit was rolled back and no money appeared from a refused sale.
    assert balance(wallet.id) == Decimal("0")
    assert holding(user.id) == Decimal("5")
    assert Transaction.query.count() == 0


def test_selling_something_never_owned_changes_nothing():
    user = make_user()
    wallet = make_wallet(user, balance="0")
    make_stock("TEST", price="100")

    with pytest.raises(ValueError, match="You do not have"):
        StocksService().sell_stock(user.id, "TEST", wallet.id, 1)

    assert balance(wallet.id) == Decimal("0")


def test_sell_needs_a_usd_wallet_the_caller_owns():
    user, other = make_user(), make_user()
    eur = make_wallet(user, balance="0", currency=WalletCurrencyType.EUR)
    theirs = make_wallet(other, balance="0")
    make_stock("TEST", price="100")
    db.session.add(UserStockWallet(user_id=user.id, symbol="TEST", quantity=5))
    db.session.commit()

    for wallet in (eur, theirs):
        with pytest.raises(DataNotFound, match="USD wallet"):
            StocksService().sell_stock(user.id, "TEST", wallet.id, 1)

    assert holding(user.id) == Decimal("5")
    assert balance(eur.id) == Decimal("0")
    assert balance(theirs.id) == Decimal("0")
