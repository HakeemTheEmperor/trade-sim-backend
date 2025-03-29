from functools import wraps
from flask import request, jsonify
from flask_jwt_extended import get_jwt, jwt_required
import os

demo_api_key = os.getenv("JWT_SECRET_KEY", "default_secret_key")
def require_api_key():
    def decorator(f):
        @wraps(f)  # Preserves the original function's metadata (name, docstring, etc.)
        def decorated_function(*args, **kwargs):
            api_key = request.headers.get("X-API-Key")
            if not api_key or api_key != demo_api_key:
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