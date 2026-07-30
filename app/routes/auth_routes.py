from flask import Blueprint, jsonify, request
from flask_jwt_extended import (
    jwt_required,
    get_jwt,
    get_jwt_identity,
    set_access_cookies,
    unset_jwt_cookies,
)
import os
from ..models.user import UserRoles
from ..services.auth_service import AuthService
from ..utils.auth_utils import role_required
from ..utils.rate_limit import rate_limit

bp = Blueprint("auth", __name__, url_prefix="/api/v1/auth")
auth_service = AuthService()

@bp.route("/admin-signup", methods=['POST'])
@role_required(UserRoles.SUPER_ADMIN.value)
def admin_create():
    data = request.get_json()
    required_fields = ["first_name", "last_name", "email", "password", "username"]
    if not data or not all(key in data and data[key].strip() for key in required_fields):
        return jsonify({"error": f"Missing or invalid required fields ({', '.join(required_fields)})"}), 400

    cleaned_data = {key: data[key].strip() for key in required_fields}

    new_user = auth_service.admin_signup(
        first_name=cleaned_data["first_name"],
        last_name=cleaned_data["last_name"],
        email=cleaned_data["email"],
        password=cleaned_data["password"],
        username=cleaned_data["username"]
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
    
    new_user = auth_service.create_user(
        first_name=cleaned_data["first_name"],
        last_name=cleaned_data["last_name"],
        email=cleaned_data["email"],
        password=cleaned_data["password"],
        username=cleaned_data["username"]
    )
    # Deliberately NO session here: create_user has emailed a 6-digit code and
    # the account stays inactive until it's entered at /verify-email, which is
    # where the cookie is finally issued. Nothing but the user's own submitted
    # email is echoed back, so this response leaks nothing.
    return jsonify({
        "message": "Account created. Enter the 6-digit code we emailed you to activate it.",
        "email": new_user.email,
        "verification_required": True,
        "status": "VERIFICATION REQUIRED"
    }), 201


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
        if not user.is_verified:
            # Reached only after a CORRECT password, so this reveals nothing to
            # anyone who doesn't already hold the credentials. The client keys
            # off `status`, never the prose, and the message is kept vague on
            # purpose. No cookie is set — an unverified account gets no session.
            return jsonify({
                "message": "Your account has not been verified.",
                "status": "ACCOUNT_UNVERIFIED",
                "email": user.email
            }), 403
        access_token = auth_service.generate_token(user)
        response = jsonify({
            "message": "Sign-in successful",
            "user": user.to_dict()})
        set_access_cookies(response, access_token)
        return response, 200
    return jsonify({'message': 'Invalid email or password'}), 401


@bp.route('/verify-email', methods=['POST'])
# Public (no session exists yet). The per-code attempt cap in
# EmailVerificationCode.verify is the real brute-force defence; this caps the
# request volume any one client can generate on top of that.
@rate_limit(max_requests=10, window_seconds=300)
def verify_email():
    data = request.get_json()

    required_fields = ['email', 'otp']
    if not data or not all(key in data and str(data[key]).strip() for key in required_fields):
        return jsonify({"error": "Missing or invalid required fields (email, otp)"}), 400

    email = data['email'].strip()
    otp = str(data['otp']).strip()

    # Raises ValueError -> clean 400 with a single generic message for every
    # failure mode. See AuthService.verify_email.
    user, newly_verified = auth_service.verify_email(email, otp)

    # Verification also signs the user in: they just proved control of the
    # address one step ago, so making them retype the password buys nothing.
    access_token = auth_service.generate_token(user)
    response = jsonify({
        "message": "Email verified successfully" if newly_verified else "Your email is already verified",
        "user": user.to_dict()
    })
    set_access_cookies(response, access_token)
    return response, 200


@bp.route('/resend-otp', methods=['POST'])
# Tighter than verify-email: this one causes an outbound email, so it's both a
# spam vector and a drain on the provider's daily quota. Backed by a per-account
# 60s cooldown that survives restarts (the limiter's counters don't).
@rate_limit(max_requests=3, window_seconds=300)
def resend_otp():
    data = request.get_json()

    if not data or not data.get('email', '').strip():
        return jsonify({"error": "Missing or invalid required field (email)"}), 400

    auth_service.resend_verification(data['email'].strip())

    # Fixed response, always 200: unknown address, already-verified account and
    # active cooldown must be indistinguishable, or this becomes a free
    # account-enumeration endpoint (it takes no password).
    return jsonify({
        "message": "If that account exists and is unverified, a new code has been sent."
    }), 200


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
        # Tokens predating the verification feature carry no such claim; treat a
        # missing value as verified, matching how the migration grandfathered
        # existing accounts.
        "is_verified": claims.get("is_verified", True),
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
# Accepts old_password, so this has the same brute-force surface as /signin and
# needs the same protection. Keyed by user id (see rate_limit._client_key).
@rate_limit(max_requests=5, window_seconds=300)
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
    




