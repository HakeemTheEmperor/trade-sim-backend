from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..services.notification_service import NotificationService

bp = Blueprint("notifications", __name__, url_prefix="/api/v1/notifications")
notification_service = NotificationService()


@bp.route("/", methods=["GET"])
@jwt_required()
def list_notifications():
    user_id = get_jwt_identity()
    page = request.args.get("page", 1, type=int)
    rows = request.args.get("rows", 20, type=int)
    return jsonify(notification_service.list_for_user(user_id, page, rows)), 200


@bp.route("/unread-count", methods=["GET"])
@jwt_required()
def unread_count():
    user_id = get_jwt_identity()
    return jsonify({"unread_count": notification_service.unread_count(user_id)}), 200


@bp.route("/<int:notification_id>/read", methods=["POST"])
@jwt_required()
def mark_read(notification_id):
    user_id = get_jwt_identity()
    return jsonify(notification_service.mark_read(user_id, notification_id)), 200


@bp.route("/read-all", methods=["POST"])
@jwt_required()
def mark_all_read():
    user_id = get_jwt_identity()
    return jsonify(notification_service.mark_all_read(user_id)), 200
