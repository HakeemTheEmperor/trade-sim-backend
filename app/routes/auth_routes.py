from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt, get_jwt_identity
import os
from ..services.auth_service import AuthService
from ..utils.auth_utils import require_api_key, role_required

bp = Blueprint("auth", __name__, url_prefix="/api/v1/auth")
auth_service = AuthService()

@bp.route("/admin-signup", methods=['POST'])
@require_api_key()
@role_required('SUPERADMIN')
def admin_create():
    data = request.get_json()
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
@require_api_key()
def user_signup():
    data = request.get_json()
    if not data or not all(key in data for key in ["first_name", "last_name", "email", "password"]):
        return jsonify({"error": "Missing required fields (first_name, last_name, email, password)"}), 400
    
    try:
        new_user = auth_service.create_user(
            first_name=data["first_name"],
            last_name=data["last_name"],
            email=data["email"],
            password=data["password"]
        )
        access_token = auth_service.generate_token(new_user)
        return jsonify({
            "message": "User created successfully", 
            "token": access_token,
            "user": new_user.to_dict()}), 201
    except ValueError as e:
        raise
    
@bp.route('/signin', methods=['POST'])
@require_api_key()
def signin():
    data = request.get_json()
    if not data or not all(key in data for key in ['email', 'password']):
        return jsonify({"error": "Missing required fields (email, password)"}), 400
    
    user = auth_service.authenticate_user(data['email'], data['password'])
    if user:
        access_token = auth_service.generate_token(user)
        return jsonify({
            "message": "Sign-in successful",
            "token": access_token,
            "user": user.to_dict()}), 200
    return jsonify({'error': 'Invalid email or password'}), 401

@bp.route("/debug-token", methods=["GET"])
@jwt_required()
def debug_token():
    claims = get_jwt()
    user_id = get_jwt_identity()
    return jsonify({"user_id": user_id, "claims": claims})

@bp.route("/logout", methods=["GET"])
@require_api_key()
@jwt_required()
def logout():
    jti = get_jwt()["jti"]
    logged_out = auth_service.logout(jti)
    if logged_out:
        return jsonify({"message": "You have successfully logged out of your account", "status_code": 200, "status": "SIGN OUT SUCCESS"}), 200
    return jsonify({"message": "We were unable to log you out of your account", "status_code": 400, "status": "SIGN OUT FAIL"}), 400

@bp.route("/reset-password", methods=["POST"])
@require_api_key()
@jwt_required()
def reset_password():
    jti = get_jwt()["jti"]
    user_id = get_jwt_identity()
    data = request.get_json()
    
    if not data or not all(key in data for key in ['old_password', 'new_password']):
        return jsonify({"error": "Missing required fields (old_password, new_password)"}),
    
    user = auth_service.reset_password(user_id, data)
    logged_out = auth_service.logout(jti)
    if user and logged_out:
        return jsonify({
            "message": "Password reset successfully, please sign in again",
            "user": user
        }), 200
    return jsonify({'message': 'Invalid data entered'}), 400
    
    

