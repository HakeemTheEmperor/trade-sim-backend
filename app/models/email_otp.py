import secrets
from datetime import datetime, timedelta, timezone

from werkzeug.security import check_password_hash, generate_password_hash

from .. import db

# How long a freshly issued code stays usable. Long enough to survive a slow
# mail hop, short enough that a leaked inbox isn't a standing key.
OTP_TTL_MINUTES = 10
# A 6-digit code is only a million possibilities, so the attempt cap — not the
# code length — is what actually makes guessing infeasible. Counted per code, so
# requesting a new one resets it (and invalidates the old code).
MAX_ATTEMPTS = 5
# Floor between sends, to stop the endpoint being used to mailbomb an address
# and to stay inside Brevo's daily quota. Enforced here as well as by the
# @rate_limit decorator on the route: that one is keyed by client IP and resets
# on deploy, this one is per-account and survives restarts.
RESEND_COOLDOWN_SECONDS = 60

OTP_LENGTH = 6


def _now():
    return datetime.now(timezone.utc)


def _as_aware(value):
    """Treat a naive datetime read back from the DB as UTC.

    Columns are DateTime(timezone=True), but depending on the driver/connection
    a value can come back naive. Comparing naive to aware raises TypeError, so
    normalise before every comparison rather than trusting the round-trip.
    """
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


class EmailVerificationCode(db.Model):
    """A single-use OTP proving a user controls the email they signed up with.

    Only the hash is stored, for the same reason passwords are hashed: a
    database read must not hand out live credentials. Codes are one-at-a-time
    per user — issuing a new one consumes any outstanding code, so an old email
    sitting in an inbox can't be replayed.
    """
    __tablename__ = "email_verification_codes"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    code_hash = db.Column(db.String(255), nullable=False)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False)
    attempts = db.Column(db.Integer, nullable=False, default=0)
    # Set when the code is used, superseded by a newer one, or burned by hitting
    # the attempt cap. Non-null means "no longer usable", whatever the reason.
    consumed_at = db.Column(db.DateTime(timezone=True), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), default=db.func.current_timestamp(), nullable=False)

    __table_args__ = (
        db.Index("ix_email_otp_user_created", "user_id", "created_at"),
    )

    @classmethod
    def _latest(cls, user_id):
        return (
            cls.query.filter_by(user_id=user_id)
            .order_by(cls.created_at.desc(), cls.id.desc())
            .first()
        )

    @classmethod
    def issue(cls, user):
        """Create a new code for ``user`` and return it in cleartext.

        The cleartext is returned rather than stored: the caller hands it
        straight to the mailer and drops it. Nothing else can ever read it back.
        """
        now = _now()
        # Supersede anything still outstanding so only the newest code works.
        cls.query.filter(
            cls.user_id == user.id,
            cls.consumed_at.is_(None),
        ).update({"consumed_at": now}, synchronize_session=False)

        # randbelow, not random.randint — this is a credential, so it needs a
        # CSPRNG. Zero-padded so every code is exactly 6 digits.
        code = f"{secrets.randbelow(10 ** OTP_LENGTH):0{OTP_LENGTH}d}"
        record = cls(
            user_id=user.id,
            code_hash=generate_password_hash(code),
            expires_at=now + timedelta(minutes=OTP_TTL_MINUTES),
        )
        db.session.add(record)
        db.session.commit()
        return code

    @classmethod
    def verify(cls, user, code):
        """Check ``code`` against the user's newest live code.

        Returns True only on an exact match of an unconsumed, unexpired code
        that hasn't burned through its attempts. Every wrong guess is counted,
        and the code is burned outright once the cap is reached so an attacker
        can't keep guessing against the same target without triggering a resend
        (which is itself rate limited).
        """
        record = cls._latest(user.id)
        if record is None or record.consumed_at is not None:
            return False

        now = _now()
        if _as_aware(record.expires_at) <= now:
            record.consumed_at = now
            db.session.commit()
            return False

        record.attempts += 1
        if record.attempts > MAX_ATTEMPTS:
            record.consumed_at = now
            db.session.commit()
            return False

        if not check_password_hash(record.code_hash, str(code)):
            # Commit the incremented attempt count — without this the counter
            # would roll back and the cap would never bite.
            db.session.commit()
            return False

        record.consumed_at = now
        db.session.commit()
        return True

    @classmethod
    def seconds_until_resend_allowed(cls, user):
        """0 if a new code can be sent now, else seconds left on the cooldown."""
        record = cls._latest(user.id)
        if record is None:
            return 0
        elapsed = (_now() - _as_aware(record.created_at)).total_seconds()
        return max(0, int(RESEND_COOLDOWN_SECONDS - elapsed))
