import logging
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
from ..models.user import User
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
        league = League.query.get(league_id)
        if not league:
            raise DataNotFound("League not found")
        # The owner deletes rather than leaves. Transferring ownership on the way
        # out is nicer, but it adds a state to reason about for a case that a
        # small league can handle socially — and an ownerless league can't be
        # deleted by anyone.
        if int(league.owner_id) == int(user_id):
            raise ValueError(
                "You own this league — delete it instead of leaving"
            )
        membership = LeagueMembership.query.filter_by(
            league_id=league_id, user_id=int(user_id)
        ).first()
        if not membership:
            raise DataNotFound("You're not in that league")
        db.session.delete(membership)
        db.session.commit()
        return {"message": f"You have left {league.name}"}

    def delete_league(self, user_id, league_id):
        league = League.query.get(league_id)
        if not league:
            raise DataNotFound("League not found")
        if int(league.owner_id) != int(user_id):
            raise DataNotFound("League not found")
        name = league.name
        # Memberships cascade.
        db.session.delete(league)
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
        """Latest known equity per user, from the daily snapshots.

        Reading snapshots rather than valuing live is what makes a 50-member
        table affordable: one indexed query instead of members x holdings x
        price lookups on every page load.

        Anyone without a snapshot yet — a brand new account, or any account on
        the first day before the 01:00 job has run — is valued live so they
        aren't silently missing from the table. Bounded by the member cap.
        """
        latest = {}
        if not user_ids:
            return latest

        newest = (db.session.query(
                    EquitySnapshot.user_id,
                    func.max(EquitySnapshot.captured_on).label("day"))
                  .filter(EquitySnapshot.user_id.in_(user_ids))
                  .group_by(EquitySnapshot.user_id)
                  .subquery())

        rows = (db.session.query(EquitySnapshot)
                .join(newest,
                      (EquitySnapshot.user_id == newest.c.user_id)
                      & (EquitySnapshot.captured_on == newest.c.day))
                .all())
        for row in rows:
            latest[int(row.user_id)] = (Decimal(row.equity), row.captured_on)

        missing = [uid for uid in user_ids if uid not in latest]
        if missing:
            prices, rates = {}, {}
            for uid in missing:
                equity, _, _ = self.leaderboard.compute_equity(uid, prices, rates)
                latest[uid] = (equity, None)
        return latest

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
        as_of = None
        for participant in participants:
            uid = int(participant.user_id)
            value, captured_on = equity.get(uid, (Decimal(0), None))
            if captured_on and (as_of is None or captured_on > as_of):
                as_of = captured_on
            baseline = Decimal(participant.baseline_equity)
            change = ((value - baseline) / baseline * 100) if baseline > 0 else Decimal(0)
            rows.append({
                "user_id": uid,
                "username": participant.user.username if participant.user else None,
                "return_percent": float(round(change, 2)),
            })

        return {
            "league": league.to_dict(
                member_count=len(member_ids),
                is_owner=int(league.owner_id) == int(user_id),
            ),
            "season": season.to_dict(),
            "entries": self._ranked(rows),
            # Standings are as of the last snapshot, so the client can say so
            # rather than implying they're live.
            "as_of": as_of.isoformat() if as_of else None,
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
            value, _ = equity.get(uid, (Decimal(0), None))
            change = (value - STARTING_EQUITY_USD) / STARTING_EQUITY_USD * 100
            rows.append({
                "user_id": uid,
                "username": user.username,
                "return_percent": float(round(change, 2)),
            })

        return {
            "league": league.to_dict(
                member_count=len(member_ids),
                is_owner=int(league.owner_id) == int(user_id),
            ),
            "entries": self._ranked(rows),
        }

    def _ranked(self, rows):
        rows.sort(key=lambda r: r["return_percent"], reverse=True)
        for position, row in enumerate(rows, start=1):
            row["rank"] = position
        return rows
