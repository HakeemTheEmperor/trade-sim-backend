from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.user_service import UserService
from ..utils.auth_utils import require_api_key, role_required

bp = Blueprint("user", __name__, url_prefix="/users")
user_service = UserService()

""" @bp.route("/all", methods=["GET"])
@require_api_key()
@role_required() """