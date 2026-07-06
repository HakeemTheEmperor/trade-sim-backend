from enum import Enum

from .. import db


class NotificationType(Enum):
    SHADOW_INVITE = "SHADOW_INVITE"      # you were invited to shadow someone
    SHADOW_TRADE = "SHADOW_TRADE"        # a subject you shadow made a trade
    SHADOW_ACCEPTED = "SHADOW_ACCEPTED"  # someone accepted your invite


class Notification(db.Model):
    """Unified in-app notification feed (polled by the client for v1).

    payload is a small JSON blob whose shape depends on ``type``. For
    SHADOW_TRADE it MUST NOT contain any quantity, amount, or balance — only
    ``{actor_id, actor_name, action, symbol, ...}`` — to preserve the shadow
    privacy rule.
    """
    __tablename__ = "notifications"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    type = db.Column(db.Enum(NotificationType), nullable=False)
    payload = db.Column(db.JSON, nullable=False, default=dict)
    is_read = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime(timezone=True), default=db.func.current_timestamp(), nullable=False)

    __table_args__ = (
        db.Index("ix_notification_user_read_created", "user_id", "is_read", "created_at"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "type": self.type.value,
            "payload": self.payload,
            "is_read": self.is_read,
            "created_at": self.created_at.isoformat(),
        }
