import logging
import os
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)


def report_stale_prices(app):
    """Log tickers that are listed but not receiving prices.

    OTC symbols and thinly traded ADRs can have no IEX trades at all, so the
    poller skips them and their price silently freezes. The window defaults to
    5 days so a long weekend or a market holiday doesn't trigger it.

    Returns ``{"no_price": [...], "stale": [...]}``.
    """
    with app.app_context():
        from .. import db
        from ..models.stock_available import AvailableStocks
        from ..models.stock_price import StockPrice

        days = int(os.getenv("STALE_PRICE_DAYS") or 5)
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        no_price = sorted(
            symbol for (symbol,) in
            db.session.query(AvailableStocks.symbol)
            .outerjoin(StockPrice, StockPrice.symbol == AvailableStocks.symbol)
            .filter(StockPrice.id.is_(None))
            .all()
        )
        stale = sorted(
            symbol for (symbol,) in
            db.session.query(StockPrice.symbol).filter(StockPrice.updated_at < cutoff).all()
        )

        if no_price:
            logger.warning("%d tickers have no price yet: %s", len(no_price), ", ".join(no_price[:25]))
        if stale:
            logger.warning("%d tickers not updated in %d days: %s",
                           len(stale), days, ", ".join(stale[:25]))
        if not no_price and not stale:
            logger.info("Price health OK: every ticker has a recent price")
        return {"no_price": no_price, "stale": stale}
