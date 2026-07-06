from enum import Enum

from .. import db


class ShadowStatus(Enum):
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    DECLINED = "DECLINED"
    REVOKED = "REVOKED"


class InitiatedBy(Enum):
    # Who started the link. SUBJECT = an invite (default flow, accepted by the
    # shadow). SHADOW = a request (only possible when the subject is discoverable,
    # accepted by the subject). See feature-shadow.md.
    SUBJECT = "SUBJECT"
    SHADOW = "SHADOW"


class ShadowLink(db.Model):
    """A follow relationship: a subject is shadowed by a shadow.

    The subject is the followed user; the shadow is the follower who sees the
    subject's trade events (symbol + action only, never quantity/amount).
    """
    __tablename__ = "shadow_links"

    id = db.Column(db.Integer, primary_key=True)
    subject_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    shadow_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    status = db.Column(db.Enum(ShadowStatus), default=ShadowStatus.PENDING, nullable=False)
    initiated_by = db.Column(db.Enum(InitiatedBy), default=InitiatedBy.SUBJECT, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=db.func.current_timestamp(), nullable=False)
    responded_at = db.Column(db.DateTime(timezone=True), nullable=True)
    updated_at = db.Column(db.DateTime(timezone=True), default=db.func.current_timestamp(), onupdate=db.func.current_timestamp(), nullable=False)

    subject = db.relationship("User", foreign_keys=[subject_id])
    shadow = db.relationship("User", foreign_keys=[shadow_id])

    __table_args__ = (
        # One link per (subject, shadow) pair. A declined/revoked pair is flipped
        # back to PENDING rather than inserting a duplicate.
        db.UniqueConstraint("subject_id", "shadow_id", name="uq_shadow_link_pair"),
        db.Index("ix_shadow_link_subject_status", "subject_id", "status"),
        db.Index("ix_shadow_link_shadow_status", "shadow_id", "status"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "subject_id": self.subject_id,
            "shadow_id": self.shadow_id,
            "status": self.status.value,
            "initiated_by": self.initiated_by.value,
            "created_at": self.created_at.isoformat(),
            "responded_at": self.responded_at.isoformat() if self.responded_at else None,
        }
