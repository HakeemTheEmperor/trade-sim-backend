import logging
from collections import defaultdict
from decimal import Decimal

from sqlalchemy import func

from .. import db
from ..custom_exceptions import AlreadyExists, DataNotFound, LimitReached
from ..models.league import (
    League,
    LeagueMembership,
    generate_join_code,
    max_league_members,
    max_leagues_per_user,
)
from ..models.leaderboard import STARTING_EQUITY_USD, EquitySnapshot, SeasonParticipant
from ..models.stock_price import StockPrice
from ..models.user import User
from ..models.user_stock_wallet import UserStockWallet
from ..models.wallet import Wallet
from ..utils.validation_utils import quantize_money
from .leaderboard_service import LeaderboardService

logger = logging.getLogger(__name__)

# A code collision is astronomically unlikely (~8.5e11 combinations) but the
# column is UNIQUE, so retry rather than hand the user a 500 on the one-in-a-
# billion case.
CODE_ATTEMPTS = 5


class LeagueService:
    def __init__(self):
        self.leaderboard = LeaderboardService()

    # ------------------------------------------------------------ membership

    def create_league(self, user_id, name):
        name = (name or "").strip()
        if not name:
            raise ValueError("Give your league a name")
        if len(name) > 60:
            raise ValueError("League names are limited to 60 characters")

        self._assert_under_league_cap(user_id)

        for _ in range(CODE_ATTEMPTS):
            code = generate_join_code()
            if not League.query.filter_by(join_code=code).first():
                break
        else:
            raise RuntimeError("Could not allocate a join code; please try again")

        league = League(name=name, join_code=code, owner_id=int(user_id))
        db.session.add(league)
        db.session.flush()
        db.session.add(LeagueMembership(league_id=league.id, user_id=int(user_id)))
        db.session.commit()
        return league.to_dict(member_count=1, is_owner=True)

    def join_league(self, user_id, code):
        code = (code or "").strip().upper()
        if not code:
            raise ValueError("Enter a join code")

        self._assert_under_league_cap(user_id)

        # Locked for the duration: the member cap is a COUNT, which no database
        # constraint can express, so two people joining simultaneously at 49
        # would both pass an unlocked check. Same pattern as the balance checks
        # in transfer_funds and buy_stocks.
        league = League.query.filter_by(join_code=code).with_for_update().first()
        if not league:
            # Deliberately identical to any other failure: this endpoint takes a
            # guessable-length code, so it must not confirm which codes exist.
            raise DataNotFound("That join code isn't valid")

        existing = LeagueMembership.query.filter_by(
            league_id=league.id, user_id=int(user_id)
        ).first()
        if existing:
            raise AlreadyExists("You're already in this league")

        members = LeagueMembership.query.filter_by(league_id=league.id).count()
        if members >= max_league_members():
            raise LimitReached(
                f"This league is full ({max_league_members()} members)"
            )

        db.session.add(LeagueMembership(league_id=league.id, user_id=int(user_id)))
        db.session.commit()
        return league.to_dict(member_count=members + 1, is_owner=False)

    def leave_league(self, user_id, league_id):
        """Leave a league. Anyone can, including the owner.

        The owner used to be forbidden from leaving, on the reasoning that
        transferring ownership added a state to reason about. That was only
        tenable while an owner could delete instead — now that deletion requires
        being alone, forbidding the owner to leave would imprison them in a
        league they can neither exit nor close. Transferring is the cheaper of
        the two problems.
        """
        league = League.query.filter_by(id=league_id).with_for_update().first()
        if not league:
            raise DataNotFound("League not found")
        membership = LeagueMembership.query.filter_by(
            league_id=league_id, user_id=int(user_id)
        ).first()
        if not membership:
            raise DataNotFound("You're not in that league")

        name = league.name
        db.session.delete(membership)
        db.session.flush()

        remaining = (LeagueMembership.query
                     .filter_by(league_id=league_id)
                     .order_by(LeagueMembership.joined_at.asc(), LeagueMembership.id.asc())
                     .all())

        if not remaining:
            # Last one out closes it. Nobody can see an empty league's code, so
            # leaving it behind would be litter nobody could ever clear.
            db.session.delete(league)
            db.session.commit()
            return {"message": f"You have left {name}. It was empty, so it has been closed."}

        if int(league.owner_id) == int(user_id):
            # Longest-standing remaining member inherits it.
            league.owner_id = remaining[0].user_id

        db.session.commit()
        return {"message": f"You have left {name}"}

    def delete_league(self, user_id, league_id):
        """Close a league — owner only, and only once they're the last one in it.

        Deleting a populated league would let an owner who doesn't like the
        standings erase them for everybody. The table is a shared object; one
        member shouldn't be able to destroy it unilaterally. An owner who wants
        out leaves instead, and ownership passes on.
        """
        league = League.query.filter_by(id=league_id).with_for_update().first()
        if not league:
            raise DataNotFound("League not found")
        # Same answer as a missing league: a non-owner shouldn't learn that a
        # league exists but isn't theirs.
        if int(league.owner_id) != int(user_id):
            raise DataNotFound("League not found")

        members = LeagueMembership.query.filter_by(league_id=league_id).count()
        if members > 1:
            raise ValueError(
                "You can't delete a league other people are in. Leave it instead — "
                "ownership passes to another member."
            )

        name = league.name
        db.session.delete(league)   # memberships cascade
        db.session.commit()
        return {"message": f"{name} has been deleted"}

    def my_leagues(self, user_id):
        memberships = (LeagueMembership.query
                       .filter_by(user_id=int(user_id))
                       .order_by(LeagueMembership.joined_at.asc())
                       .all())
        if not memberships:
            return []

        league_ids = [m.league_id for m in memberships]
        counts = dict(
            db.session.query(LeagueMembership.league_id, func.count(LeagueMembership.id))
            .filter(LeagueMembership.league_id.in_(league_ids))
            .group_by(LeagueMembership.league_id)
            .all()
        )
        return [
            m.league.to_dict(
                member_count=counts.get(m.league_id, 0),
                is_owner=int(m.league.owner_id) == int(user_id),
            )
            for m in memberships
            if m.league is not None
        ]

    def _assert_under_league_cap(self, user_id):
        count = LeagueMembership.query.filter_by(user_id=int(user_id)).count()
        if count >= max_leagues_per_user():
            raise LimitReached(
                f"You can be in at most {max_leagues_per_user()} leagues. "
                "Leave one to join another."
            )

    def _member_ids(self, user_id, league_id):
        """Members of a league the caller actually belongs to.

        Non-members get the same answer as a non-existent league, so league ids
        can't be enumerated to discover who is in what.
        """
        membership = LeagueMembership.query.filter_by(
            league_id=league_id, user_id=int(user_id)
        ).first()
        if not membership:
            raise DataNotFound("League not found")
        rows = LeagueMembership.query.filter_by(league_id=league_id).all()
        return membership.league, [int(r.user_id) for r in rows]

    # ---------------------------------------------------------------- tables

    def _equity_for(self, user_ids):
        """Live equity per user, in three queries for the whole cohort.

        This used to read the nightly equity_snapshots table, which made a table
        cheap but meant a trade didn't move the standings until 01:00 the next
        morning — in a trading app, the one thing people open the leaderboard to
        see. The cost I was avoiding was never "live", it was compute_equity's
        per-user loop; batched over the cohort it's three queries regardless of
        member count, which is cheaper than the snapshot path was for a small
        league and still fine at the 50-member cap.

        Snapshots stay for what they're actually for: daily history, and the
        time series any "return this week" view would need.
        """
        if not user_ids:
            return {}

        wallet_rows = (db.session.query(Wallet.user_id, Wallet.currency, Wallet.balance)
                       .filter(Wallet.user_id.in_(user_ids)).all())
        holding_rows = (db.session.query(UserStockWallet.user_id,
                                         UserStockWallet.symbol,
                                         UserStockWallet.quantity)
                        .filter(UserStockWallet.user_id.in_(user_ids)).all())

        symbols = {row.symbol for row in holding_rows}
        prices = {}
        if symbols:
            prices = {
                symbol: Decimal(price)
                for symbol, price in db.session.query(
                    StockPrice.symbol, StockPrice.current_price
                ).filter(StockPrice.symbol.in_(symbols)).all()
            }

        totals = defaultdict(Decimal)
        rates = {}
        for user_id, currency, balance in wallet_rows:
            # Shared with the snapshot job on purpose: both must value a wallet
            # the same way or the two would disagree about the same account.
            totals[int(user_id)] += self.leaderboard._to_usd(
                Decimal(balance or 0), currency, rates)
        for user_id, symbol, quantity in holding_rows:
            # A symbol with no price is worth nothing rather than crashing the
            # table for everyone in the league.
            totals[int(user_id)] += Decimal(quantity or 0) * prices.get(symbol, Decimal(0))

        return {uid: quantize_money(totals.get(uid, Decimal(0))) for uid in user_ids}

    def season_table(self, user_id, league_id):
        league, member_ids = self._member_ids(user_id, league_id)
        season = self.leaderboard.current_season()
        if not season:
            raise DataNotFound("No season is currently running")

        participants = (SeasonParticipant.query
                        .filter(SeasonParticipant.season_id == season.id,
                                SeasonParticipant.user_id.in_(member_ids))
                        .all())
        equity = self._equity_for([int(p.user_id) for p in participants])

        rows = []
        for participant in participants:
            uid = int(participant.user_id)
            value = equity.get(uid, Decimal(0))
            baseline = Decimal(participant.baseline_equity)
            change = ((value - baseline) / baseline * 100) if baseline > 0 else Decimal(0)
            rows.append({
                "user_id": uid,
                "username": participant.user.username if participant.user else None,
                # Three decimals to match what the UI renders. At two the
                # backend was rounding away everything below 0.005%, while
                # PercentageChange padded the result out to three digits — so a
                # trade whose real cost was -0.001% displayed as a confident
                # "0.000%", which reads as "nothing happened" rather than
                # "too small to show".
                "return_percent": float(round(change, 3)),
            })

        return {
            "league": league.to_dict(
                member_count=len(member_ids),
                is_owner=int(league.owner_id) == int(user_id),
            ),
            "season": season.to_dict(),
            "entries": self._ranked(rows),
            "viewer_ranked": any(r["user_id"] == int(user_id) for r in rows),
        }

    def career_table(self, user_id, league_id):
        league, member_ids = self._member_ids(user_id, league_id)
        equity = self._equity_for(member_ids)

        rows = []
        for uid in member_ids:
            user = User.query.get(uid)
            if not user:
                continue
            value = equity.get(uid, Decimal(0))
            change = (value - STARTING_EQUITY_USD) / STARTING_EQUITY_USD * 100
            rows.append({
                "user_id": uid,
                "username": user.username,
                # Three decimals to match what the UI renders. At two the
                # backend was rounding away everything below 0.005%, while
                # PercentageChange padded the result out to three digits — so a
                # trade whose real cost was -0.001% displayed as a confident
                # "0.000%", which reads as "nothing happened" rather than
                # "too small to show".
                "return_percent": float(round(change, 3)),
            })

        return {
            "league": league.to_dict(
                member_count=len(member_ids),
                is_owner=int(league.owner_id) == int(user_id),
            ),
            "entries": self._ranked(rows),
        }

    def _ranked(self, rows):
        """Sort by return and assign standard competition ranks.

        Equal returns share a rank, and the next distinct value takes the rank
        of its position — 1, 2, 2, 4 rather than 1, 2, 3, 4. Sequential ranks
        made a tie look like a result: two members both on 0.000% were shown as
        1st and 2nd, with the order decided by nothing more than who was
        enrolled in the season first.

        Ties are ordered by username so that the ORDER is at least deterministic
        rather than an artefact of database row order. They still share a rank,
        so nothing about that ordering claims one beat the other.
        """
        rows.sort(key=lambda r: (-r["return_percent"], (r["username"] or "").lower()))

        previous_value = None
        previous_rank = 0
        for position, row in enumerate(rows, start=1):
            if previous_value is not None and row["return_percent"] == previous_value:
                row["rank"] = previous_rank
            else:
                row["rank"] = position
                previous_rank = position
                previous_value = row["return_percent"]
        return rows
