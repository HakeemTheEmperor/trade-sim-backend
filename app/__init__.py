from flask import Flask, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import JWTManager
from datetime import timedelta
import os
from dotenv import load_dotenv
from .error_handlers import register_error_handlers

db = SQLAlchemy()
jwt = JWTManager()

@jwt.token_in_blocklist_loader
def check_if_token_revoked(jwt_header, jwt_payload):
    from .models.revokedtoken import RevokedToken
    jti = jwt_payload["jti"]
    return RevokedToken.is_revoked(jti)

@jwt.invalid_token_loader
def invalid_token_callback(error):
    return jsonify({"error": "Invalid token. Please log in again."}), 401

@jwt.expired_token_loader
def expired_token_callback(jwt_header, jwt_payload):
    return jsonify({"error": "Token has expired. Please log in again."}), 401

@jwt.unauthorized_loader
def missing_token_callback(error):
    return jsonify({"error": "Missing token. Authorization required."}), 401


def create_admin():
    from .models.user import User
    from werkzeug.security import generate_password_hash
    
    admin_email = os.getenv("ADMIN_EMAIL")
    admin_password = os.getenv("ADMIN_PASSWORD")
    
    existing_admin = User.query.filter_by(email=admin_email).first()
    if not existing_admin:
        admin_user = User(
            email=admin_email,
            first_name="Super",
            last_name="Admin",
            role="admin"
        )
        admin_user.set_password(admin_password)
        db.session.add(admin_user)
        db.session.commit()
        print("Admin user created successfully")
    else:
        print("Admin user already exists")

def create_app():
    load_dotenv()
    app = Flask(__name__)
    
    # Connect to Postgresql running in Docker
    app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("SQLALCHEMY_DATABASE_URI", "postgresql://admin:secret@localhost:5432/myappdb")
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = os.getenv("SQLALCHEMY_TRACK_MODIFICATIONS", "False").lower() == "true"
    app.config["JWT_SECRET_KEY"] = os.getenv("JWT_SECRET_KEY", "SomesuPersecretsUPERrandomstri123456789")
    app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(hours=int(os.getenv("JWT_ACCESS_TOKEN_EXPIRES", "6")))
    app.config["JWT_BLACKLIST_ENABLED"] = True  # Enable token blacklisting
    app.config["JWT_BLACKLIST_TOKEN_CHECKS"] = ["access", "refresh"]
    
    # Initialize SQLAlchemy
    db.init_app(app)
    
    # Initialize JWT
    jwt.init_app(app)
    
    # Import models to ensure they're mapped
    from .models.user import User
    from .models.transactions import Transaction
    from .models.wallet import Wallet
    from .models.revokedtoken import RevokedToken
    from .models.exchangerate import ExchangeRate
    
    # Register Error Handlers
    register_error_handlers(app)
    
    # Register blueprints
    from .routes.auth_routes import bp as auth_bp
    from .routes.wallet_routes import bp as wallet_bp
    
    app.register_blueprint(auth_bp)
    app.register_blueprint(wallet_bp)
    
    # Create tables
    with app.app_context():
        db.create_all()
        create_admin()

    return app