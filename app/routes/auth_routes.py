from flask import Blueprint, jsonify, request
from flask_jwt_extended import (
    jwt_required,
    get_jwt,
    get_jwt_identity,
    set_access_cookies,
    unset_jwt_cookies,
)
import os
from ..services.auth_service import AuthService
from ..utils.auth_utils import role_required
from ..utils.rate_limit import rate_limit

bp = Blueprint("auth", __name__, url_prefix="/api/v1/auth")
auth_service = AuthService()

@bp.route("/admin-signup", methods=['POST'])
@role_required('SUPERADMIN')
def admin_create():
    data = request.get_json()
    required_fields = ["first_name", "last_name", "email", "password", "username"]
    if not data or not all(key in data for key in ["first_name", "last_name", "email", "password"]):
        return jsonify({"error": "Missing required fields (first_name, last_name, email, password)"}), 400
    
    new_user = auth_service.admin_signup(
        first_name=data["first_name"],
        last_name=data["last_name"],
        email=data["email"],
        password=data["password"]
    )
    return jsonify({"message": "Admin created successfully", "user": new_user}), 201

@bp.route("/signup", methods=['POST'])
@rate_limit(max_requests=10, window_seconds=60)
def user_signup():
    data = request.get_json()
    required_fields = ["first_name", "last_name", "email", "password", "username"]
    if not data or not all(key in data and data[key].strip() for key in required_fields):
        return jsonify({"error": "Missing or invalid required fields (first_name, last_name, email, password, username)"}), 400

    # Strip extra whitespaces from all values
    cleaned_data = {key: data[key].strip() for key in required_fields}
    
    try:
        new_user = auth_service.create_user(
            first_name=cleaned_data["first_name"],
            last_name=cleaned_data["last_name"],
            email=cleaned_data["email"],
            password=cleaned_data["password"],
            username=cleaned_data["username"]
        )
        access_token = auth_service.generate_token(new_user)
        # Token goes into an HttpOnly cookie (set_access_cookies), not the body.
        response = jsonify({
            "message": "User created successfully",
            "user": new_user.to_dict()})
        set_access_cookies(response, access_token)
        return response, 201
    except ValueError as e:
        raise
    
@bp.route('/signin', methods=['POST'])
@rate_limit(max_requests=5, window_seconds=60)
def signin():
    data = request.get_json()
    
    required_fields = ['email', 'password']
    if not data or not all(key in data and data[key].strip() for key in required_fields):
        return jsonify({"error": "Missing or invalid required fields (email, password)"}), 400
    
    cleaned_data = {key: data[key].strip() for key in required_fields}
    
    user = auth_service.authenticate_user(cleaned_data['email'], cleaned_data['password'])
    if user:
        access_token = auth_service.generate_token(user)
        response = jsonify({
            "message": "Sign-in successful",
            "user": user.to_dict()})
        set_access_cookies(response, access_token)
        return response, 200
    return jsonify({'message': 'Invalid email or password'}), 401


@bp.route("/me", methods=["GET"])
@jwt_required()
def me():
    # Lets the SPA confirm the session and recover basic identity after a reload,
    # since the token is no longer readable in JS. Reads the JWT claims (no DB hit).
    claims = get_jwt()
    return jsonify({"user": {
        "id": get_jwt_identity(),
        "first_name": claims.get("first_name"),
        "last_name": claims.get("last_name"),
        "email": claims.get("email"),
        "role": claims.get("role"),
    }}), 200

@bp.route("/logout", methods=["POST"])
@jwt_required()
def logout():
    jti = get_jwt()["jti"]
    logged_out = auth_service.logout(jti)
    if logged_out:
        response = jsonify({"message": "You have successfully logged out of your account", "status_code": 200, "status": "SIGN OUT SUCCESS"})
        unset_jwt_cookies(response)
        return response, 200
    return jsonify({"message": "We were unable to log you out of your account", "status_code": 400, "status": "SIGN OUT FAIL"}), 400

@bp.route("/reset-password", methods=["POST"])
@jwt_required()
def reset_password():
    jti = get_jwt()["jti"]
    user_id = get_jwt_identity()
    data = request.get_json()
    
    if not data or not all(key in data for key in ['old_password', 'new_password']):
        return jsonify({"error": "Missing required fields (old_password, new_password)"}), 400

    user = auth_service.reset_password(user_id, data)
    logged_out = auth_service.logout(jti)
    if user and logged_out:
        response = jsonify({
            "message": "Password reset successfully, please sign in again"
        })
        unset_jwt_cookies(response)
        return response, 200
    return jsonify({'message': 'Invalid data entered'}), 400
    




