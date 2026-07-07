import logging

from ..models.notification import Notification, NotificationType
from ..custom_exceptions import DataNotFound
from ..utils.enums_utils import ErrorStatuses
from ..utils.validation_utils import clamp_pagination
from .. import db

logger = logging.getLogger(__name__)


class NotificationService:
    def create(self, user_id, notif_type, payload, commit=True):
        """Create a single notification. Callers that batch (e.g. the trade hook)
        pass commit=False and flush/commit themselves."""
        notification = Notification(user_id=user_id, type=notif_type, payload=payload)
        db.session.add(notification)
        if commit:
            db.session.commit()
        return notification

    def list_for_user(self, user_id, page=1, rows=20):
        page, rows = clamp_pagination(page, rows, default_rows=20)
        paginated = (
            Notification.query
            .filter_by(user_id=user_id)
            .order_by(Notification.created_at.desc())
            .paginate(page=page, per_page=rows, error_out=False)
        )
        return {
            "notifications": [n.to_dict() for n in paginated.items],
            "total": paginated.total,
            "page": paginated.page,
            "per_page": paginated.per_page,
            "pages": paginated.pages,
        }

    def unread_count(self, user_id):
        return Notification.query.filter_by(user_id=user_id, is_read=False).count()

    def mark_read(self, user_id, notification_id):
        notification = Notification.query.filter_by(id=notification_id, user_id=user_id).first()
        if not notification:
            raise DataNotFound("Notification not found", ErrorStatuses.USER_NOT_FOUND.value)
        notification.is_read = True
        db.session.commit()
        return {"message": "Notification marked as read"}

    def mark_all_read(self, user_id):
        updated = (
            Notification.query
            .filter_by(user_id=user_id, is_read=False)
            .update({"is_read": True})
        )
        db.session.commit()
        return {"message": "All notifications marked as read", "updated": updated}
