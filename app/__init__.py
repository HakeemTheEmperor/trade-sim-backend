import atexit
from flask import Flask, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import JWTManager
from datetime import timedelta
from flask_cors import CORS
from flask_swagger_ui import get_swaggerui_blueprint
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import os
import threading
from dotenv import load_dotenv
from .error_handlers import register_error_handlers
from .websocket_listener import WebSocketListener

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
    from .models.user import User, UserRoles
    from werkzeug.security import generate_password_hash
    
    admin_email = os.getenv("ADMIN_EMAIL")
    admin_password = os.getenv("ADMIN_PASSWORD")
    
    existing_admin = User.query.filter_by(email=admin_email).first()
    if not existing_admin:
        admin_user = User(
            email=admin_email,
            first_name="Super",
            last_name="Admin",
            username="Supes",
            role=UserRoles.SUPER_ADMIN
        )
        admin_user.set_password(admin_password)
        db.session.add(admin_user)
        db.session.commit()
        print("Admin user created successfully")
    else:
        print("Admin user already exists")

def seed_available_stock():
    from .models.stock_available import AvailableStocks
    default_symbols = ["AAPL", "NVDA", "MSFT", "AMZN", "GOOG", "META", "BRK-B", "TSM", "TSLA", "WMT", "JPM", "V", "MA", "ORCL", "UNH", "XOM", "NFLX", "PG", "HD", "KO", "TMUS", "CVX", "NESN.SW", "005930.KS", "TM", "PM", "IBM", "MCD", "AXP", "DIS", "SHEL", "GS", "ADBE", "SIE.DE", "CAT", "CBA.AX", "XIACF", "UBER", "SONY", "SHOP", "UL", "TTE", "SBUX", "SPOT", "NKE", "INTC", "UPS", "RACE", "ABNB"]
    for symbol in default_symbols:
        if not AvailableStocks.query.filter_by(symbol=symbol).first():
            db.session.add(AvailableStocks(symbol=symbol))
    db.session.commit()
    print("Default available symbols seeded")

def create_app():
    load_dotenv()
    app = Flask(__name__)
    
    SWAGGER_URL = os.getenv("SWAGGER_URL")
    API_URL = os.getenv("API_URL")
    
    swaggerui_blueprint = get_swaggerui_blueprint(SWAGGER_URL, API_URL, config={"app_name": "Stock Trade Simulator Web Api"})

    
    # Connect to Postgresql running in Docker
    app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("SQLALCHEMY_DATABASE_URI")
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = os.getenv("SQLALCHEMY_TRACK_MODIFICATIONS", "False").lower() == "true"
    app.config["JWT_SECRET_KEY"] = os.getenv("JWT_SECRET_KEY")
    app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(hours=int(os.getenv("JWT_ACCESS_TOKEN_EXPIRES", "6")))
    app.config["JWT_BLACKLIST_ENABLED"] = True  # Enable token blacklisting
    app.config["JWT_BLACKLIST_TOKEN_CHECKS"] = ["access", "refresh"]

    # Initialize SQLAlchemy
    db.init_app(app)
    
    # Initialize JWT
    jwt.init_app(app)
    
    CORS(app, resources={r"/*": {"origins": "*"}})
    # Import models to ensure they're mapped
    from .models.user import User
    from .models.transactions import Transaction
    from .models.wallet import Wallet
    from .models.revokedtoken import RevokedToken
    from .models.exchangerate import ExchangeRate
    from .models.stock_available import AvailableStocks
    from .models.stock_price import StockPrice
    from .models.stock_history import StockHistory
    from .models.watch_list import WatchList
    from .data_seed import DataSeed
    from .utils.update_history import UpdateHistory
    

    
    # Register Error Handlers
    register_error_handlers(app)
    
    # Register blueprints
    from .routes.auth_routes import bp as auth_bp
    from .routes.wallet_routes import bp as wallet_bp
    from .routes.transactions_routes import bp as transaction_bp
    from .routes.stocks_route import bp as stocks_bp
    from .routes.user_routes import bp as user_bp
    from .routes.watchlist_routes import bp as watchlist_bp
    
    app.register_blueprint(auth_bp)
    app.register_blueprint(wallet_bp)
    app.register_blueprint(transaction_bp)
    app.register_blueprint(stocks_bp)
    app.register_blueprint(user_bp)
    app.register_blueprint(watchlist_bp)
    app.register_blueprint(swaggerui_blueprint, url_prefix=SWAGGER_URL)
    

    
    # Create tables
    with app.app_context():
        db.create_all()
        create_admin()
        
        update_history = UpdateHistory()
        #DataSeed.load_available_stocks(app)
        #update_history.update_price_history(app)
        
        scheduler = BackgroundScheduler()
        scheduler.add_job(DataSeed.load_available_stocks, CronTrigger(hour=0, minute=0, second=0), args=[app])
        scheduler.add_job(update_history.update_price_history, CronTrigger(hour=0, minute=5, second=0), args=[app])
        scheduler.start()
        atexit.register(lambda: scheduler.shutdown())
        
        websocket_listener = WebSocketListener(app)
        websocket_listener.start()

    return app