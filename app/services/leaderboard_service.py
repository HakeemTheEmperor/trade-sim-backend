import logging
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import or_

from .. import db
from ..custom_exceptions import DataNotFound
from ..models.leaderboard import (
    STARTING_EQUITY_USD,
    EquitySnapshot,
    Season,
    SeasonParticipant,
)
from ..models.shadow_link import ShadowLink, ShadowStatus
from ..models.stock_price import StockPrice
from ..models.user import User
from ..models.user_stock_wallet import UserStockWallet
from ..models.wallet import Wallet, WalletCurrencyType
from ..utils.validation_utils import quantize_money

logger = logging.getLogger(__name__)

# Quarterly by default. A year is too long for a friend group's attention and
# too long to recover from a bad start — go down early and the board is dead for
# nine months. Override per deployment, but prefer changing it at a boundary.
DEFAULT_SEASON_LENGTH_DAYS = 90


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

    def _friend_ids(self, user_id):
        """The user plus everyone they have an ACCEPTED shadow link with, in
        either direction. Friend boards are mutual by construction — you only
        appear on a board with someone who agreed to the link."""
        links = ShadowLink.query.filter(
            ShadowLink.status == ShadowStatus.ACCEPTED,
            or_(ShadowLink.subject_id == user_id, ShadowLink.shadow_id == user_id),
        ).all()
        ids = {int(user_id)}
        for link in links:
            ids.add(int(link.subject_id))
            ids.add(int(link.shadow_id))
        return ids

    def friend_board(self, user_id):
        """Rank the user and their accepted connections for the current season.

        Ranked on percentage return, never absolute equity. The two are
        equivalent today, but absolute breaks the moment baselines differ — and
        showing balances would contradict the privacy rule the shadow feature is
        built on (trade events deliberately carry no amounts).
        """
        season = self.current_season()
        if not season:
            raise DataNotFound("No season is currently running")

        ids = self._friend_ids(user_id)
        participants = (SeasonParticipant.query
                        .filter(SeasonParticipant.season_id == season.id,
                                SeasonParticipant.user_id.in_(ids))
                        .all())

        prices, rates = {}, {}
        rows = []
        for participant in participants:
            equity, _, _ = self.compute_equity(participant.user_id, prices, rates)
            baseline = Decimal(participant.baseline_equity)
            # A baseline of zero can't produce a meaningful percentage. Only
            # reachable for an account that was already wiped out at season
            # start; treat it as flat rather than dividing by zero.
            change = ((equity - baseline) / baseline * 100) if baseline > 0 else Decimal(0)
            rows.append({
                "user_id": participant.user_id,
                "username": participant.user.username if participant.user else None,
                "return_percent": float(round(change, 2)),
            })

        rows.sort(key=lambda r: r["return_percent"], reverse=True)
        for position, row in enumerate(rows, start=1):
            row["rank"] = position

        return {
            "season": season.to_dict(),
            "entries": rows,
            # Told explicitly rather than left to be inferred from an absent row,
            # so the client can explain why someone isn't listed.
            "viewer_ranked": any(r["user_id"] == int(user_id) for r in rows),
        }

    def career_board(self, user_id):
        """All-time board: return since the account was funded.

        Measured against the same starting grant for everyone, which is only
        sound because that grant is the only money that ever enters an account.
        """
        ids = self._friend_ids(user_id)
        prices, rates = {}, {}
        rows = []
        for uid in ids:
            user = User.query.get(uid)
            if not user:
                continue
            equity, _, _ = self.compute_equity(uid, prices, rates)
            change = (equity - STARTING_EQUITY_USD) / STARTING_EQUITY_USD * 100
            rows.append({
                "user_id": uid,
                "username": user.username,
                "return_percent": float(round(change, 2)),
            })

        rows.sort(key=lambda r: r["return_percent"], reverse=True)
        for position, row in enumerate(rows, start=1):
            row["rank"] = position
        return {"entries": rows}
