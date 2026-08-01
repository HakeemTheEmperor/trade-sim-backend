from decimal import Decimal

from .. import db

# What every account is granted at signup (the default on Wallet.balance). The
# career board measures against this, which is only meaningful because there is
# no deposit endpoint and transfers are own-wallet only — so this is the ONLY
# way money enters the system, and every account starts from the same line.
STARTING_EQUITY_USD = Decimal("100000.00")


class Season(db.Model):
    """A ranking period. Money persists across seasons; only the ranking resets.

    Seasons exist because a lifetime board decays into a measure of who joined
    earliest: someone a year ahead has compounded longer, and a newcomer cannot
    catch up by being better, only by waiting. Resetting the *baseline* each
    season keeps it a contest of skill over the same window, without deleting
    anyone's portfolio.
    """
    __tablename__ = "seasons"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    starts_at = db.Column(db.DateTime(timezone=True), nullable=False)
    ends_at = db.Column(db.DateTime(timezone=True), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=db.func.current_timestamp(), nullable=False)

    __table_args__ = (
        db.Index("ix_season_window", "starts_at", "ends_at"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "starts_at": self.starts_at.isoformat(),
            "ends_at": self.ends_at.isoformat(),
        }


class SeasonParticipant(db.Model):
    """A user's starting line for one season.

    A row here is what makes someone rankable. Rows are written once, when the
    season opens, for every account that already exists — so anyone who signs up
    mid-season simply has no row and is not ranked until the next one. That is
    the intended exclusion, not an oversight: a late joiner measured over a
    shorter window is not comparable to someone who ran the full season.
    """
    __tablename__ = "season_participants"

    id = db.Column(db.Integer, primary_key=True)
    season_id = db.Column(db.Integer, db.ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    # Equity in USD at the moment the season opened. Return is measured from
    # here rather than from the starting grant, so a player who is already up
    # 300% isn't credited with that gain again every season.
    baseline_equity = db.Column(db.Numeric(18, 4), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=db.func.current_timestamp(), nullable=False)

    user = db.relationship("User", foreign_keys=[user_id])

    __table_args__ = (
        db.UniqueConstraint("season_id", "user_id", name="uq_season_participant"),
        db.Index("ix_season_participant_season", "season_id"),
    )


class EquitySnapshot(db.Model):
    """One user's total equity on one day, in USD.

    Written daily by the scheduler. Ranking needs cash plus holdings marked to
    current prices for every user; computing that per leaderboard request would
    be users x holdings x price lookups on every page load. Snapshots also give
    the time series that any "return over the last week" view needs.
    """
    __tablename__ = "equity_snapshots"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    captured_on = db.Column(db.Date, nullable=False)
    equity = db.Column(db.Numeric(18, 4), nullable=False)
    cash = db.Column(db.Numeric(18, 4), nullable=False)
    holdings = db.Column(db.Numeric(18, 4), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=db.func.current_timestamp(), nullable=False)

    __table_args__ = (
        # One row per user per day: the job is idempotent, so a retry or a
        # double-fire updates rather than duplicating.
        db.UniqueConstraint("user_id", "captured_on", name="uq_equity_snapshot_day"),
        db.Index("ix_equity_snapshot_user_day", "user_id", "captured_on"),
    )

    def to_dict(self):
        return {
            "captured_on": self.captured_on.isoformat(),
            "equity": self.equity,
            "cash": self.cash,
            "holdings": self.holdings,
        }
