from functools import wraps
from flask import request, jsonify
from flask_jwt_extended import get_jwt, jwt_required
import hmac
import os

def require_api_key():
    def decorator(f):
        @wraps(f)  # Preserves the original function's metadata (name, docstring, etc.)
        def decorated_function(*args, **kwargs):
            # Read at call time so it can never be resolved before load_dotenv() runs.
            # NOTE: this is the public client key (sent by the browser), and it is
            # deliberately NOT the JWT signing secret. JWT_SECRET_KEY must stay
            # server-only so a leaked API key cannot be used to forge tokens.
            expected_key = os.getenv("API_KEY")
            provided_key = request.headers.get("X-API-Key")
            # Fail closed if the server is misconfigured, and use a constant-time
            # comparison to avoid leaking the key via response timing.
            if (
                not expected_key
                or not provided_key
                or not hmac.compare_digest(provided_key, expected_key)
            ):
                return jsonify({"message": "Invalid or missing API key", "status_code": 401, "status": "INVALID API KEY"}), 401
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def role_required(required_role):
    def decorator(f):
        @wraps(f)
        @jwt_required()
        def wrapper(*args, **kwargs):
            claims = get_jwt()
            user_role = claims.get("role")
            print(user_role)
            print(required_role)
            
            if user_role != required_role:
                return jsonify({
                    "message": "Forbidden: You do not have the required role to access this endpoint",
                    "status_code": 403,
                    "status": "FORBIDDEN"
                }), 403
            return f(*args, **kwargs)
        return wrapper
    return decorator