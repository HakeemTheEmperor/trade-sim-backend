import logging
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from .. import db
from ..models.leaderboard import EquitySnapshot, Season, SeasonParticipant
from ..models.stock_price import StockPrice
from ..models.user import User
from ..models.user_stock_wallet import UserStockWallet
from ..models.wallet import Wallet, WalletCurrencyType
from ..utils.validation_utils import quantize_money

logger = logging.getLogger(__name__)


def _as_aware(value):
    """Treat a naive datetime from the DB as UTC before comparing it."""
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value

# Quarterly. A year is too long for a friend group's attention and too long to
# recover from a bad start — go down early and the board is dead for nine months.
# Override per deployment, but prefer changing it at a boundary.
DEFAULT_SEASON_LENGTH_DAYS = 90

# How far into a season an account can still be created and be ranked in it.
#
# Without this the rule is brutally binary: sign up one minute after a season
# opens and you sit unrankable for the whole quarter, which for a young app is
# every new user. A grace window keeps the fairness intent — someone joining in
# the closing weeks can't be measured against people who ran the full period —
# while making the common case work. At 30 days on a 90-day season, the window
# covers the first third.
#
# Set to 0 to exclude everyone not present at the open; set it to the season
# length to rank everybody always.
DEFAULT_SEASON_JOIN_GRACE_DAYS = 30


def season_length_days():
    raw = os.getenv("SEASON_LENGTH_DAYS", str(DEFAULT_SEASON_LENGTH_DAYS)).strip()
    try:
        days = int(raw)
    except ValueError:
        logger.warning("SEASON_LENGTH_DAYS=%r is not an integer; using %d", raw, DEFAULT_SEASON_LENGTH_DAYS)
        return DEFAULT_SEASON_LENGTH_DAYS
    if days < 1:
        logger.warning("SEASON_LENGTH_DAYS=%d is not positive; using %d", days, DEFAULT_SEASON_LENGTH_DAYS)
        return DEFAULT_SEASON_LENGTH_DAYS
    return days


def season_join_grace_days():
    raw = os.getenv("SEASON_JOIN_GRACE_DAYS", str(DEFAULT_SEASON_JOIN_GRACE_DAYS)).strip()
    try:
        days = int(raw)
    except ValueError:
        logger.warning("SEASON_JOIN_GRACE_DAYS=%r is not an integer; using %d",
                       raw, DEFAULT_SEASON_JOIN_GRACE_DAYS)
        return DEFAULT_SEASON_JOIN_GRACE_DAYS
    if days < 0:
        logger.warning("SEASON_JOIN_GRACE_DAYS=%d is negative; using %d",
                       days, DEFAULT_SEASON_JOIN_GRACE_DAYS)
        return DEFAULT_SEASON_JOIN_GRACE_DAYS
    return days


class LeaderboardService:
    # ---------------------------------------------------------------- equity

    def compute_equity(self, user_id, price_cache=None, rate_cache=None):
        """Total worth of an account in USD: cash across all wallets, plus
        holdings marked to the current price.

        The caches are passed in by the daily job so valuing N users costs one
        price read per symbol rather than one per user per symbol.
        """
        prices = price_cache if price_cache is not None else {}
        rates = rate_cache if rate_cache is not None else {}

        cash = Decimal(0)
        for wallet in Wallet.query.filter_by(user_id=user_id).all():
            cash += self._to_usd(Decimal(wallet.balance or 0), wallet.currency, rates)

        holdings = Decimal(0)
        for holding in UserStockWallet.query.filter_by(user_id=user_id).all():
            price = prices.get(holding.symbol)
            if price is None:
                record = StockPrice.query.filter_by(symbol=holding.symbol).first()
                # A symbol with no price is worth nothing here rather than
                # crashing the whole run — one bad symbol must not stop every
                # other user being valued.
                price = Decimal(record.current_price) if record else Decimal(0)
                prices[holding.symbol] = price
            holdings += Decimal(holding.quantity or 0) * price

        cash = quantize_money(cash)
        holdings = quantize_money(holdings)
        return quantize_money(cash + holdings), cash, holdings

    def _to_usd(self, amount, currency, rates):
        """Convert a wallet balance to USD. Everything is ranked in one currency
        or the numbers aren't comparable."""
        if currency == WalletCurrencyType.USD:
            return amount
        key = currency.value
        if key not in rates:
            # Imported here rather than at module scope: WalletService imports
            # heavy provider config, and the leaderboard is also loaded by the
            # scheduler at boot.
            from .wallet_service import WalletService
            try:
                rates[key] = Decimal(WalletService().get_exchange_rate(currency, WalletCurrencyType.USD))
            except Exception:
                logger.exception("No USD rate for %s; valuing that wallet at 0", key)
                rates[key] = Decimal(0)
        return amount * rates[key]

    # -------------------------------------------------------------- snapshots

    def snapshot_all(self, app=None):
        """Write today's equity for every user. Idempotent per (user, day)."""
        if app is not None:
            with app.app_context():
                return self._snapshot_all()
        return self._snapshot_all()

    def _snapshot_all(self):
        today = datetime.now(timezone.utc).date()
        prices, rates = {}, {}
        written = 0
        for (user_id,) in db.session.query(User.id).all():
            try:
                equity, cash, holdings = self.compute_equity(user_id, prices, rates)
                existing = EquitySnapshot.query.filter_by(user_id=user_id, captured_on=today).first()
                if existing:
                    existing.equity, existing.cash, existing.holdings = equity, cash, holdings
                else:
                    db.session.add(EquitySnapshot(
                        user_id=user_id, captured_on=today,
                        equity=equity, cash=cash, holdings=holdings,
                    ))
                written += 1
            except Exception:
                # One user's bad data must not cost everyone else their snapshot.
                logger.exception("Could not snapshot user %s", user_id)
        db.session.commit()
        logger.info("Wrote %d equity snapshots for %s", written, today)
        return written

    # ---------------------------------------------------------------- seasons

    def current_season(self):
        now = datetime.now(timezone.utc)
        return (Season.query
                .filter(Season.starts_at <= now, Season.ends_at > now)
                .order_by(Season.starts_at.desc())
                .first())

    def open_season(self, name=None, starts_at=None, length_days=None):
        """Start a season and freeze every existing user's baseline.

        Only accounts that exist at this moment get a participant row, which is
        what excludes mid-season joiners from this season's ranking.
        """
        now = starts_at or datetime.now(timezone.utc)
        days = length_days or season_length_days()
        season = Season(
            name=name or f"Season starting {now.date().isoformat()}",
            starts_at=now,
            ends_at=now + timedelta(days=days),
        )
        db.session.add(season)
        db.session.flush()

        prices, rates = {}, {}
        enrolled = 0
        for (user_id,) in db.session.query(User.id).all():
            equity, _, _ = self.compute_equity(user_id, prices, rates)
            db.session.add(SeasonParticipant(
                season_id=season.id, user_id=user_id, baseline_equity=equity,
            ))
            enrolled += 1
        db.session.commit()
        logger.info("Opened %r with %d participants", season.name, enrolled)
        return season

    def enrol_new_user(self, user_id):
        """Enrol a just-created account into the running season, if it opened
        recently enough. Returns True if a participant row was written.

        Baseline is the account's equity right now — the starting grant — so a
        late joiner is measured over their own window from their own starting
        line, not handed anyone else's head start.

        Never raises: an account that fails to enrol is unranked until the next
        season, which is a far better outcome than a signup that 500s.
        """
        try:
            season = self.current_season()
            if not season:
                return False
            grace = season_join_grace_days()
            age = _as_aware(datetime.now(timezone.utc)) - _as_aware(season.starts_at)
            if age > timedelta(days=grace):
                logger.info(
                    "User %s signed up %s into the season (grace %dd); "
                    "not ranked until the next season", user_id, age, grace)
                return False
            if SeasonParticipant.query.filter_by(
                season_id=season.id, user_id=int(user_id)
            ).first():
                return True
            equity, _, _ = self.compute_equity(user_id)
            db.session.add(SeasonParticipant(
                season_id=season.id, user_id=int(user_id), baseline_equity=equity,
            ))
            db.session.commit()
            logger.info("Enrolled user %s in season %s", user_id, season.id)
            return True
        except Exception:
            db.session.rollback()
            logger.exception("Could not enrol user %s in the current season", user_id)
            return False

    def ensure_season(self, app=None):
        """Open a new season if none is currently running. Safe to call often."""
        if app is not None:
            with app.app_context():
                return self._ensure_season()
        return self._ensure_season()

    def _ensure_season(self):
        season = self.current_season()
        if season:
            return season
        return self.open_season()

    # ------------------------------------------------------------ leaderboard
