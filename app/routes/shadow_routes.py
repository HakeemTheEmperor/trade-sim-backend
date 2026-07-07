from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..services.shadow_service import ShadowService

bp = Blueprint("shadow", __name__, url_prefix="/api/v1/shadow")
shadow_service = ShadowService()


@bp.route("/invite", methods=["POST"])
@jwt_required()
def invite():
    subject_id = get_jwt_identity()
    data = request.get_json() or {}
    result = shadow_service.invite(
        subject_id,
        username=data.get("invitee_username"),
        email=data.get("invitee_email"),
    )
    return jsonify(result), 201


@bp.route("/invite/<int:link_id>/accept", methods=["POST"])
@jwt_required()
def accept_invite(link_id):
    shadow_id = get_jwt_identity()
    return jsonify(shadow_service.accept(shadow_id, link_id)), 200


@bp.route("/invite/<int:link_id>/decline", methods=["POST"])
@jwt_required()
def decline_invite(link_id):
    shadow_id = get_jwt_identity()
    return jsonify(shadow_service.decline(shadow_id, link_id)), 200


@bp.route("/invites", methods=["GET"])
@jwt_required()
def incoming_invites():
    shadow_id = get_jwt_identity()
    return jsonify({"invites": shadow_service.list_incoming_invites(shadow_id)}), 200


@bp.route("/shadows", methods=["GET"])
@jwt_required()
def my_shadows():
    subject_id = get_jwt_identity()
    return jsonify({"shadows": shadow_service.list_shadows(subject_id)}), 200


@bp.route("/shadows/<int:link_id>", methods=["DELETE"])
@jwt_required()
def remove_shadow(link_id):
    subject_id = get_jwt_identity()
    return jsonify(shadow_service.remove_shadow(subject_id, link_id)), 200


@bp.route("/following", methods=["GET"])
@jwt_required()
def following():
    shadow_id = get_jwt_identity()
    return jsonify({"following": shadow_service.list_following(shadow_id)}), 200


@bp.route("/following/<int:link_id>", methods=["DELETE"])
@jwt_required()
def stop_following(link_id):
    shadow_id = get_jwt_identity()
    return jsonify(shadow_service.stop_following(shadow_id, link_id)), 200
