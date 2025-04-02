from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.user_service import UserService
from ..models.user import UserRoles
from ..utils.auth_utils import require_api_key, role_required

bp = Blueprint("user", __name__, url_prefix="/api/v1/users")
user_service = UserService()

@bp.route("/all", methods=["GET"])
@require_api_key()
@role_required(UserRoles.SUPER_ADMIN.value)
def get_all_users():
    users = user_service.get_all_users()
    return jsonify({"message": "Users retrieved successfully", "data": users})

@bp.route("/user", methods=["GET"])
@require_api_key()
@jwt_required()
def get_user():
    user_id = get_jwt_identity()
    user = user_service.get_user_by_id(user_id)
    return jsonify({"message": "User retrieved successfully", "data": user})


@bp.route('/user/edit', methods=['POST'])
@require_api_key()
@jwt_required()
def edit_user_info():
    user_id = get_jwt_identity()
    data = request.get_json()
    response = user_service.update_user_data(user_id, data)
    return jsonify(response), 200