"""Shared bulk write into ``stock_price`` for every live-price source.

Both the Finnhub websocket listener and the Alpaca poller land their prices
here, so the previous_price / percentage_change bookkeeping lives in one place.
"""
import logging

from sqlalchemy import case, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from .. import db
from ..models.stock_available import AvailableStocks
from ..models.stock_price import StockPrice

logger = logging.getLogger(__name__)


def write_prices(prices, skip_unchanged=False):
    """Bulk-upsert ``{symbol: Decimal}`` into ``stock_price``.

    Must be called inside an app context. Commits on success; on failure the
    caller is responsible for ``db.session.rollback()``.

    ``skip_unchanged`` drops symbols whose price equals the stored one. Pollers
    need this because they re-read a price that hasn't traded since the last
    cycle, and writing it would roll previous_price forward and zero the
    percentage change. The websocket only reports actual trades, so it leaves
    this off.

    Returns the number of symbols written.
    """
    if not prices:
        return 0

    # stock_price.symbol is a foreign key, and one unknown symbol would fail the
    # whole statement, so drop anything we don't list.
    known = set(db.session.scalars(
        select(AvailableStocks.symbol).where(AvailableStocks.symbol.in_(list(prices)))
    ))
    unknown = set(prices) - known
    if unknown:
        logger.warning("Ignoring prices for %d unlisted symbols: %s",
                       len(unknown), ", ".join(sorted(unknown)[:10]))
    prices = {s: p for s, p in prices.items() if s in known}
    if not prices:
        return 0

    if db.engine.dialect.name == "postgresql":
        return _upsert_postgres(prices, skip_unchanged)
    return _write_orm(prices, skip_unchanged)


def _upsert_postgres(prices, skip_unchanged):
    """One INSERT ... ON CONFLICT for every symbol, instead of a round trip each.

    In DO UPDATE, ``stock_price.current_price`` is the row's OLD value and every
    SET expression sees the old row, so previous_price and percentage_change are
    computed against the price being replaced.
    """
    stmt = pg_insert(StockPrice).values([
        {
            "symbol": symbol,
            "current_price": price,
            "previous_price": 0,
            "percentage_change": 0,
            "updated_at": func.now(),
        }
        for symbol, price in prices.items()
    ])
    old = StockPrice.__table__.c.current_price
    new = stmt.excluded.current_price
    stmt = stmt.on_conflict_do_update(
        index_elements=[StockPrice.__table__.c.symbol],
        set_={
            "previous_price": old,
            "current_price": new,
            "percentage_change": case((old > 0, (new - old) / old * 100), else_=0),
            "updated_at": func.now(),
        },
        where=(old != new) if skip_unchanged else None,
    ).returning(StockPrice.__table__.c.symbol)

    written = len(db.session.execute(stmt).all())
    db.session.commit()
    return written


def _write_orm(prices, skip_unchanged):
    """Row-by-row fallback for non-Postgres databases (local SQLite runs)."""
    existing = {
        s.symbol: s
        for s in StockPrice.query.filter(StockPrice.symbol.in_(list(prices))).all()
    }
    written = 0
    for symbol, price in prices.items():
        stock = existing.get(symbol)
        if stock:
            if skip_unchanged and stock.current_price == price:
                continue
            if stock.current_price > 0:
                percentage_change = ((price - stock.current_price) / stock.current_price) * 100
            else:
                percentage_change = 0
            stock.previous_price = stock.current_price
            stock.current_price = price
            stock.percentage_change = percentage_change
        else:
            stock = StockPrice(symbol=symbol, current_price=price)
        db.session.add(stock)
        written += 1
    db.session.commit()
    return written
