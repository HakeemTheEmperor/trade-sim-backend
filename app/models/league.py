import logging
import os
import secrets

from .. import db

logger = logging.getLogger(__name__)

# Ambiguous characters removed (I/1/L, O/0) because these get read aloud and
# retyped from a screenshot. 8 characters from 31 is ~8.5e11 combinations, which
# is not brute-forceable at the join endpoint's rate limit.
JOIN_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
JOIN_CODE_LENGTH = 8

DEFAULT_MAX_LEAGUE_MEMBERS = 50
DEFAULT_MAX_LEAGUES_PER_USER = 5


def _positive_int_env(name, default):
    raw = os.getenv(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError:
        logger.warning("%s=%r is not an integer; using %d", name, raw, default)
        return default
    if value < 1:
        logger.warning("%s=%d is not positive; using %d", name, value, default)
        return default
    return value


def max_league_members():
    """Cap chosen for the product, not the database.

    50 covers any real friend group, course or office team with headroom, keeps
    the table to a single screen (no pagination to build), and bounds the blast
    radius when someone inevitably posts a join code publicly — the worst case
    is 50 strangers seeing your percentage, not 5000. A snapshot-backed table
    would happily serve far more; that isn't the constraint that matters.
    """
    return _positive_int_env("MAX_LEAGUE_MEMBERS", DEFAULT_MAX_LEAGUE_MEMBERS)


def max_leagues_per_user():
    """A member cap alone doesn't stop one person joining hundreds of leagues,
    each one a set of strangers who can see their return. This closes the
    cheaper abuse vector."""
    return _positive_int_env("MAX_LEAGUES_PER_USER", DEFAULT_MAX_LEAGUES_PER_USER)


def generate_join_code():
    return "".join(secrets.choice(JOIN_CODE_ALPHABET) for _ in range(JOIN_CODE_LENGTH))


class League(db.Model):
    """A named, opt-in ranking group.

    Replaces the ego-centric shadow-link board. That version computed a
    different cohort per viewer, so no two people saw the same table and nobody
    could talk about "the standings" — there weren't any. A league is a shared
    object: every member sees an identical ranking.

    Note the privacy trade-off this accepts. The shadow board only ever exposed
    your return to people you had mutually agreed to link with. A join code
    exposes it to whoever holds the code. Percentages only, never balances, and
    joining is an explicit act — but it is a real shift, which is what the caps
    above are bounding.
    """
    __tablename__ = "leagues"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(60), nullable=False)
    # Stored uppercase and compared uppercase, so a code read off a screenshot
    # works regardless of how it's typed.
    join_code = db.Column(db.String(16), unique=True, nullable=False)
    owner_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=db.func.current_timestamp(), nullable=False)

    owner = db.relationship("User", foreign_keys=[owner_id])
    memberships = db.relationship(
        "LeagueMembership", back_populates="league", cascade="all, delete-orphan"
    )

    __table_args__ = (
        db.Index("ix_league_join_code", "join_code"),
    )

    def to_dict(self, member_count=None, is_owner=False):
        return {
            "id": self.id,
            "name": self.name,
            # Every member can see the code — that's how you invite the next
            # person. There's nothing to protect beyond membership itself.
            "join_code": self.join_code,
            "owner_id": self.owner_id,
            "is_owner": is_owner,
            "member_count": member_count if member_count is not None else len(self.memberships),
            "created_at": self.created_at.isoformat(),
        }


class LeagueMembership(db.Model):
    __tablename__ = "league_memberships"

    id = db.Column(db.Integer, primary_key=True)
    league_id = db.Column(db.Integer, db.ForeignKey("leagues.id", ondelete="CASCADE"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    joined_at = db.Column(db.DateTime(timezone=True), default=db.func.current_timestamp(), nullable=False)

    league = db.relationship("League", back_populates="memberships")
    user = db.relationship("User", foreign_keys=[user_id])

    __table_args__ = (
        db.UniqueConstraint("league_id", "user_id", name="uq_league_member"),
        db.Index("ix_league_membership_user", "user_id"),
        db.Index("ix_league_membership_league", "league_id"),
    )
