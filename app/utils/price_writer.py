"""Shared bulk write into ``stock_price`` for every live-price source.

Both the Finnhub websocket listener and the Alpaca poller land their prices
here, so the previous_price / percentage_change bookkeeping lives in one place.
"""
from .. import db
from ..models.stock_price import StockPrice


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

    # One query for every symbol instead of one per symbol.
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
            stock.current_price = price  # Decimal, not float
            stock.percentage_change = percentage_change
        else:
            stock = StockPrice(symbol=symbol, current_price=price)
        db.session.add(stock)
        written += 1
    db.session.commit()
    return written
