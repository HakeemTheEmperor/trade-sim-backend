from functools import wraps
from flask import jsonify
from flask_jwt_extended import get_jwt, jwt_required

def role_required(required_role):
    def decorator(f):
        @wraps(f)
        @jwt_required()
        def wrapper(*args, **kwargs):
            claims = get_jwt()
            user_role = claims.get("role")

            if user_role != required_role:
                return jsonify({
                    "message": "Forbidden: You do not have the required role to access this endpoint",
                    "status_code": 403,
                    "status": "FORBIDDEN"
                }), 403
            return f(*args, **kwargs)
        return wrapper
    return decorator