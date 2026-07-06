import logging
from datetime import datetime, timezone

from ..models.shadow_link import ShadowLink, ShadowStatus, InitiatedBy
from ..models.notification import NotificationType
from ..models.user import User
from ..custom_exceptions import AlreadyExists, DataNotFound, LimitReached, MissingProperties
from ..utils.enums_utils import ErrorStatuses
from .notification_service import NotificationService
from .. import db

logger = logging.getLogger(__name__)

# A subject may have at most this many accepted shadows; a shadow may follow at
# most this many subjects.
MAX_SHADOWS_PER_SUBJECT = 20
MAX_FOLLOWING_PER_SHADOW = 10


class ShadowService:
    def __init__(self):
        self.notifications = NotificationService()

    def _get_invitee(self, username=None, email=None):
        if not username and not email:
            raise MissingProperties("Provide the username or email of the person to invite")
        query = User.query
        if username:
            user = query.filter_by(username=username).first()
        else:
            user = query.filter_by(email=email).first()
        if not user:
            raise DataNotFound("No user found with those details", ErrorStatuses.USER_NOT_FOUND.value)
        return user

    def invite(self, subject_id, username=None, email=None):
        """Subject invites another user to become their shadow."""
        invitee = self._get_invitee(username, email)
        if invitee.id == int(subject_id):
            raise ValueError("You cannot invite yourself")

        link = ShadowLink.query.filter_by(subject_id=subject_id, shadow_id=invitee.id).first()
        if link:
            if link.status == ShadowStatus.ACCEPTED:
                raise AlreadyExists("This user is already one of your shadows")
            if link.status == ShadowStatus.PENDING:
                raise AlreadyExists("You already have a pending invite to this user")
            # Previously DECLINED/REVOKED — flip back to PENDING (no duplicate row).
            link.status = ShadowStatus.PENDING
            link.initiated_by = InitiatedBy.SUBJECT
            link.responded_at = None
        else:
            link = ShadowLink(
                subject_id=subject_id,
                shadow_id=invitee.id,
                status=ShadowStatus.PENDING,
                initiated_by=InitiatedBy.SUBJECT,
            )
            db.session.add(link)

        db.session.flush()  # need link.id for the notification payload
        subject = User.query.get(subject_id)
        self.notifications.create(
            user_id=invitee.id,
            notif_type=NotificationType.SHADOW_INVITE,
            payload={
                "actor_id": subject.id,
                "actor_name": subject.username,
                "link_id": link.id,
            },
            commit=False,
        )
        db.session.commit()
        return {"message": f"Shadow invite sent to {invitee.username}", "link": link.to_dict()}

    def accept(self, shadow_id, link_id):
        """Shadow accepts an invite. Enforces both caps under row locks so two
        concurrent accepts can't push either side past its limit."""
        try:
            link = ShadowLink.query.filter_by(id=link_id).with_for_update().first()
            if not link or link.shadow_id != int(shadow_id):
                raise DataNotFound("Invite not found", ErrorStatuses.USER_NOT_FOUND.value)
            if link.status == ShadowStatus.ACCEPTED:
                return {"message": "Invite already accepted", "link": link.to_dict()}
            if link.status != ShadowStatus.PENDING:
                raise ValueError("This invite is no longer pending")

            subject_count = ShadowLink.query.filter_by(
                subject_id=link.subject_id, status=ShadowStatus.ACCEPTED
            ).count()
            if subject_count >= MAX_SHADOWS_PER_SUBJECT:
                raise LimitReached("This user isn't accepting more shadows right now")

            following_count = ShadowLink.query.filter_by(
                shadow_id=shadow_id, status=ShadowStatus.ACCEPTED
            ).count()
            if following_count >= MAX_FOLLOWING_PER_SHADOW:
                raise LimitReached("You're already following the maximum number of people")

            link.status = ShadowStatus.ACCEPTED
            link.responded_at = datetime.now(timezone.utc)
            db.session.flush()

            self.notifications.create(
                user_id=link.subject_id,
                notif_type=NotificationType.SHADOW_ACCEPTED,
                payload={
                    "actor_id": int(shadow_id),
                    "actor_name": User.query.get(shadow_id).username,
                    "link_id": link.id,
                },
                commit=False,
            )
            db.session.commit()
            return {"message": "You are now shadowing this user", "link": link.to_dict()}
        except (DataNotFound, ValueError, LimitReached):
            db.session.rollback()
            raise
        except Exception as e:
            db.session.rollback()
            raise RuntimeError(f"An unexpected error occurred: {str(e)}")

    def decline(self, shadow_id, link_id):
        link = ShadowLink.query.filter_by(id=link_id, shadow_id=shadow_id).first()
        if not link:
            raise DataNotFound("Invite not found", ErrorStatuses.USER_NOT_FOUND.value)
        if link.status == ShadowStatus.PENDING:
            link.status = ShadowStatus.DECLINED
            link.responded_at = datetime.now(timezone.utc)
            db.session.commit()
        return {"message": "Invite declined"}

    def remove_shadow(self, subject_id, link_id):
        """Subject removes one of their shadows (revokes the link)."""
        link = ShadowLink.query.filter_by(id=link_id, subject_id=subject_id).first()
        if not link:
            raise DataNotFound("Shadow not found", ErrorStatuses.USER_NOT_FOUND.value)
        link.status = ShadowStatus.REVOKED
        link.responded_at = datetime.now(timezone.utc)
        db.session.commit()
        return {"message": "Shadow removed"}

    def stop_following(self, shadow_id, link_id):
        """Shadow stops following a subject (revokes the link)."""
        link = ShadowLink.query.filter_by(id=link_id, shadow_id=shadow_id).first()
        if not link:
            raise DataNotFound("You are not following this user", ErrorStatuses.USER_NOT_FOUND.value)
        link.status = ShadowStatus.REVOKED
        link.responded_at = datetime.now(timezone.utc)
        db.session.commit()
        return {"message": "You have stopped following this user"}

    def _serialize_link(self, link, other_user):
        data = link.to_dict()
        data["user"] = {"id": other_user.id, "username": other_user.username} if other_user else None
        return data

    def list_incoming_invites(self, shadow_id):
        links = (
            ShadowLink.query
            .filter_by(shadow_id=shadow_id, status=ShadowStatus.PENDING)
            .order_by(ShadowLink.created_at.desc())
            .all()
        )
        return [self._serialize_link(l, l.subject) for l in links]

    def list_shadows(self, subject_id):
        links = (
            ShadowLink.query
            .filter_by(subject_id=subject_id, status=ShadowStatus.ACCEPTED)
            .order_by(ShadowLink.responded_at.desc())
            .all()
        )
        return [self._serialize_link(l, l.shadow) for l in links]

    def list_following(self, shadow_id):
        links = (
            ShadowLink.query
            .filter_by(shadow_id=shadow_id, status=ShadowStatus.ACCEPTED)
            .order_by(ShadowLink.responded_at.desc())
            .all()
        )
        return [self._serialize_link(l, l.subject) for l in links]

    def notify_shadows(self, subject_id, action, symbol):
        """Called AFTER a trade commits. Fans out a privacy-safe SHADOW_TRADE
        notification (symbol + action only — never quantity/amount) to every
        currently-accepted shadow. Best-effort: any failure is logged and
        swallowed so it can never affect the trade that already committed."""
        try:
            links = ShadowLink.query.filter_by(
                subject_id=subject_id, status=ShadowStatus.ACCEPTED
            ).all()
            if not links:
                return
            subject = User.query.get(subject_id)
            actor_name = subject.username if subject else "Someone"
            for link in links:
                self.notifications.create(
                    user_id=link.shadow_id,
                    notif_type=NotificationType.SHADOW_TRADE,
                    payload={
                        "actor_id": int(subject_id),
                        "actor_name": actor_name,
                        "action": action,   # "BUY" or "SELL" — no quantity/amount
                        "symbol": symbol,
                    },
                    commit=False,
                )
            db.session.commit()
        except Exception:
            logger.exception("Failed to notify shadows of a trade (trade itself is unaffected)")
            db.session.rollback()
