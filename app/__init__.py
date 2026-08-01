import atexit
import logging
import re
from decimal import Decimal
from flask import Flask, Response, jsonify, request
from flask.json.provider import DefaultJSONProvider
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_jwt_extended import JWTManager
from datetime import timedelta
from flask_cors import CORS
from flask_swagger_ui import get_swaggerui_blueprint
from werkzeug.middleware.proxy_fix import ProxyFix
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import os
import threading
from dotenv import load_dotenv
from .error_handlers import register_error_handlers
from .websocket_listener import WebSocketListener

db = SQLAlchemy()
migrate = Migrate()
jwt = JWTManager()
logger = logging.getLogger(__name__)


def env_flag(name, default):
    """Read a boolean env var tolerantly.

    Values pasted into a hosting dashboard often carry stray whitespace or
    differing case ("True ", " true"), which a bare == "true" silently reads as
    False — the setting appears set but does nothing. Strip before comparing.
    """
    return os.getenv(name, default).strip().lower() in ("true", "1", "yes")


def env_int(name, default):
    """Read an integer env var without letting a typo take the service down.

    A non-numeric value here would raise inside create_app(), so the container
    would crash-loop on boot rather than start with a wrong-but-safe default.
    """
    raw = os.getenv(name, str(default)).strip()
    try:
        return int(raw)
    except ValueError:
        logger.warning("%s=%r is not an integer; falling back to %d", name, raw, default)
        return default


# Every blueprint is mounted under this prefix, and the OpenAPI paths are written
# relative to it (`/auth/signin`, not `/api/v1/auth/signin`). Anything handing
# out a base URL has to include it.
API_PREFIX = "/api/v1"


def api_base_url():
    """Public base URL clients should call, including the ``/api/v1`` prefix.

    Read from PUBLIC_API_BASE_URL, which should be the bare origin of the
    deployed API (``https://api-imockmarket.toluwalase.me``). Falls back to
    localhost on the port bootstrap.sh binds, so local runs work unconfigured.

    The prefix is appended here rather than being the caller's problem: a base
    URL missing it 404s every endpoint, and in a browser that surfaces as a
    confusing CORS preflight failure rather than a 404. A value that already
    ends in the prefix is accepted as-is so pasting the frontend's
    VITE_API_BASE_URL doesn't produce ``/api/v1/api/v1``.
    """
    configured = os.getenv("PUBLIC_API_BASE_URL", "").strip().rstrip("/")
    if not configured:
        # Matches bootstrap.sh's `--bind 0.0.0.0:${PORT:-5000}`.
        configured = f"http://localhost:{os.getenv('PORT', '5000').strip() or '5000'}"
    if configured.endswith(API_PREFIX):
        return configured
    return f"{configured}{API_PREFIX}"


class DecimalJSONProvider(DefaultJSONProvider):
    """Serialize Decimal (money columns are now Numeric/Decimal) as JSON numbers.

    Flask's default provider raises on Decimal. Emitting float keeps the API
    response shape unchanged (amounts stay JSON numbers); the exact value is
    still preserved in the database.
    """
    def default(self, o):
        if isinstance(o, Decimal):
            return float(o)
        return super().default(o)

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
            role=UserRoles.SUPER_ADMIN,
            # Seeded from env, never through the signup/OTP path — without this
            # the super-admin could never sign in.
            is_verified=True
        )
        admin_user.set_password(admin_password)
        db.session.add(admin_user)
        db.session.commit()
        logger.info("Admin user created successfully")
    else:
        logger.info("Admin user already exists")

def run_initial_seed(app):
    """Populate stocks and price history, but only if the tables are empty.

    Both jobs are re-run nightly by the scheduler and prices also stream in over
    the Finnhub websocket, so on boot they only need to fill a fresh database.
    Re-seeding every start would otherwise spend ~45 FMP requests per boot (out
    of 250/day on the free tier) to write data that's already there.

    Runs on a background thread because a first seed takes ~15 minutes:
    update_price_history sleeps 20s between symbols for Polygon's rate limit,
    which is far longer than gunicorn's worker-boot timeout.

    Trade-off: a newly added symbol in DataSeed's default list won't appear
    until the nightly job runs, since a non-empty table skips the boot seed.
    """
    from .data_seed import DataSeed
    from .models.stock_available import AvailableStocks
    from .models.stock_history import StockHistory
    from .utils.update_history import UpdateHistory

    try:
        with app.app_context():
            needs_stocks = AvailableStocks.query.first() is None
            needs_history = StockHistory.query.first() is None

        if needs_stocks:
            logger.info("No available stocks found; running initial stock seed")
            DataSeed.load_available_stocks(app)
        else:
            logger.info("Available stocks already seeded; skipping initial stock seed")

        if needs_history:
            logger.info("No price history found; running initial history backfill")
            UpdateHistory().update_price_history(app)
        else:
            logger.info("Price history already present; skipping initial backfill")
    except Exception:
        # Never let a seeding failure take down the thread silently — the app
        # itself stays up and the nightly scheduler job will retry.
        logger.exception("Initial seed failed; nightly scheduler job will retry")


def create_app():
    load_dotenv()

    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    app = Flask(__name__)
    app.json = DecimalJSONProvider(app)

    # --- Trusted proxy configuration -------------------------------------
    # Number of reverse proxies in front of this app. MEASURED, not assumed --
    # Render contributes TWO hops of its own, not one:
    #   2 = Render only (DNS-only / grey cloud)
    #   3 = Cloudflare proxied (orange cloud) -> Render
    # Confirm with LOG_CLIENT_IP=true rather than trusting these numbers; a
    # platform can change its internal topology.
    #
    # ProxyFix reads the Nth X-Forwarded-For entry FROM THE RIGHT, so this must
    # match the real topology. Setting it too high is a security bug, not a
    # cosmetic one: the extra entry is attacker-controlled, so a client could
    # forge its own IP and walk straight past the rate limiter. The default of
    # 1 deliberately under-trusts: too low means everyone collapses onto one
    # infrastructure address (over-restrictive, and obvious in testing), while
    # too high is silently exploitable. Prefer erring low.
    trusted_hops = env_int("TRUSTED_PROXY_HOPS", 1)
    # x_proto so request.is_secure reflects the original HTTPS request rather
    # than the plaintext hop inside Render's network. x_host/x_port are left
    # untrusted: nothing here needs them, and each trusted header is one more
    # value a client can influence.
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=trusted_hops, x_proto=trusted_hops)
    logger.info("ProxyFix enabled, trusting %d proxy hop(s)", trusted_hops)

    SWAGGER_URL = os.getenv("SWAGGER_URL")
    # Defaults to the templated route below rather than the raw static file, so
    # Swagger's "Try it out" targets the deployed host. Pointing this back at
    # /static/openapi.yaml still works — you just get the file's hardcoded
    # localhost server, which is the old behaviour.
    API_URL = os.getenv("API_URL", "/openapi.yaml")

    swaggerui_blueprint = get_swaggerui_blueprint(SWAGGER_URL, API_URL, config={"app_name": "Stock Trade Simulator Web Api"})

    
    # Connect to Postgresql running in Docker
    app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("SQLALCHEMY_DATABASE_URI")
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = env_flag("SQLALCHEMY_TRACK_MODIFICATIONS", "False")
    app.config["JWT_SECRET_KEY"] = os.getenv("JWT_SECRET_KEY")
    app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(hours=env_int("JWT_ACCESS_TOKEN_EXPIRES", 6))
    app.config["JWT_BLACKLIST_ENABLED"] = True  # Enable token blacklisting
    app.config["JWT_BLACKLIST_TOKEN_CHECKS"] = ["access", "refresh"]

    # --- JWT in HttpOnly cookies (instead of a client-readable header) ---
    # The token lives in an HttpOnly cookie the browser sends automatically, so
    # JavaScript (and any XSS) can't read it. FE and BE are same-site (both under
    # toluwalase.me), so SameSite=Lax works and no third-party-cookie issues apply.
    app.config["JWT_TOKEN_LOCATION"] = ["cookies"]
    # Secure=True in prod (HTTPS). Overridable so local dev over http:// can set it False.
    app.config["JWT_COOKIE_SECURE"] = env_flag("JWT_COOKIE_SECURE", "True")
    app.config["JWT_COOKIE_SAMESITE"] = os.getenv("JWT_COOKIE_SAMESITE", "Lax")
    # Double-submit CSRF: a JS-readable csrf cookie must be echoed as a header on
    # state-changing requests. Protects the cookie-auth'd endpoints against CSRF.
    app.config["JWT_COOKIE_CSRF_PROTECT"] = True
    app.config["JWT_ACCESS_COOKIE_PATH"] = "/"

    # Initialize SQLAlchemy
    db.init_app(app)

    # Initialize Alembic migrations (schema is owned by migrations, not create_all)
    migrate.init_app(app, db)

    # Initialize JWT
    jwt.init_app(app)
    
    # Allowed origins are configurable per environment (comma-separated), so the
    # frontend URL isn't hardcoded. Defaults to the production Vercel app.
    cors_origins = [
        origin.strip()
        for origin in os.getenv("CORS_ORIGINS", "https://imockmarket.vercel.app").split(",")
        if origin.strip()
    ]
    CORS(app, resources={r"/*": {"origins": cors_origins}}, supports_credentials=True)

    # Diagnostic for confirming TRUSTED_PROXY_HOPS is correct. Off by default;
    # set LOG_CLIENT_IP=true on Render, hit an endpoint from a known network
    # (e.g. your phone on mobile data), and check that the logged remote_addr
    # matches that network's public IP. Turn it back off afterwards — this logs
    # a client identifier on every request.
    if env_flag("LOG_CLIENT_IP", "false"):
        @app.before_request
        def log_client_ip():
            logger.info(
                "client-ip diagnostic: remote_addr=%s x-forwarded-for=%r path=%s",
                request.remote_addr,
                request.headers.get("X-Forwarded-For"),
                request.path,
            )

    @app.after_request
    def set_security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        # Instructs browsers to stick to HTTPS. Harmless if the API is served
        # over TLS (as it should be); ignored by browsers over plain HTTP.
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response

    @app.get("/openapi.yaml")
    def openapi_spec():
        """Serve the OpenAPI document with the deployed host substituted in.

        The file on disk carries a localhost `servers:` entry so it stays a
        valid, directly-usable spec. Served as a static file, that entry is what
        Swagger UI points "Try it out" at — which is why the deployed docs were
        firing requests at 127.0.0.1. Rewriting it here keeps env the single
        source of truth for the host without duplicating it into the YAML.

        Re-read per request: the file is small and this endpoint is human-traffic
        only, so caching it would trade a real (if minor) footgun — a stale spec
        after an edit — for nothing that matters.
        """
        spec_path = os.path.join(app.static_folder, "openapi.yaml")
        try:
            with open(spec_path, encoding="utf-8") as handle:
                spec = handle.read()
        except OSError:
            logger.exception("Could not read the OpenAPI spec at %s", spec_path)
            return jsonify({"error": "OpenAPI spec unavailable"}), 500

        # Replace the whole servers block (the `servers:` line plus every
        # indented line under it) with the single configured entry. Collapsing
        # multiple entries is intended: env is the one source of truth, so a
        # leftover second server would just be another way to call the wrong host.
        base_url = api_base_url()
        spec, replaced = re.subn(
            r"^servers:\n(?:[ \t]+.*(?:\n|$))*",
            f"servers:\n  - url: {base_url}\n",
            spec,
            count=1,
            flags=re.MULTILINE,
        )
        if not replaced:
            # Don't fail the request over it — a spec with the wrong server is
            # still far more useful than no docs at all.
            logger.warning("No servers block found in openapi.yaml; served unmodified")

        return Response(spec, mimetype="application/yaml")

    # Uptime/health probe. Runs SELECT 1 so each ping is real database activity:
    # keeps the Render free instance from idling AND counts as usage for
    # Supabase's free-tier inactivity pause.
    @app.get("/health")
    def health():
        from sqlalchemy import text
        db.session.execute(text("SELECT 1"))
        return jsonify({"status": "ok"})

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
    from .models.shadow_link import ShadowLink
    from .models.notification import Notification
    from .models.email_otp import EmailVerificationCode
    from .models.leaderboard import Season, SeasonParticipant, EquitySnapshot
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
    from .routes.shadow_routes import bp as shadow_bp
    from .routes.notification_routes import bp as notification_bp
    from .routes.leaderboard_routes import bp as leaderboard_bp
    from .routes.config_routes import bp as config_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(wallet_bp)
    app.register_blueprint(transaction_bp)
    app.register_blueprint(stocks_bp)
    app.register_blueprint(user_bp)
    app.register_blueprint(watchlist_bp)
    app.register_blueprint(shadow_bp)
    app.register_blueprint(notification_bp)
    app.register_blueprint(leaderboard_bp)
    app.register_blueprint(config_bp)
    app.register_blueprint(swaggerui_blueprint, url_prefix=SWAGGER_URL)
    

    
    # Schema is managed by Alembic migrations (`flask db upgrade`), not create_all.
    # The startup work below (admin seeding, price seeding, scheduler, websocket)
    # touches the DB and must run only on the primary app process AFTER migrations
    # have been applied. It's gated so `flask db ...` CLI commands (which set
    # RUN_BACKGROUND_JOBS=false) can build the app without triggering any of it,
    # and so extra web workers/instances don't duplicate the scheduler/websocket.
    if env_flag("RUN_BACKGROUND_JOBS", "true"):
        with app.app_context():
            create_admin()

        # Seeding runs off the main thread so gunicorn can bind its port and
        # start serving immediately (see run_initial_seed for why it's slow).
        threading.Thread(
            target=run_initial_seed, args=[app], name="initial-seed", daemon=True
        ).start()

        from .services.leaderboard_service import LeaderboardService
        leaderboard = LeaderboardService()

        # A season must exist before anyone can be ranked, and the first boot
        # after this ships has none. Enrolling here also means every account
        # that already exists gets a baseline, rather than being treated as a
        # mid-season joiner and excluded from the first season.
        with app.app_context():
            leaderboard.ensure_season()

        update_history = UpdateHistory()
        scheduler = BackgroundScheduler()
        scheduler.add_job(DataSeed.load_available_stocks, CronTrigger(hour=0, minute=0, second=0), args=[app])
        scheduler.add_job(update_history.update_price_history, CronTrigger(hour=0, minute=5, second=0), args=[app])
        # Snapshot after the nightly price refresh, so equity is valued against
        # the prices that job just wrote rather than yesterday's.
        scheduler.add_job(leaderboard.snapshot_all, CronTrigger(hour=1, minute=0, second=0), args=[app])
        # Rolls into the next season once the current one lapses. Runs daily
        # because the boundary only needs to be noticed within a day, and a
        # missed run self-corrects on the next one.
        scheduler.add_job(leaderboard.ensure_season, CronTrigger(hour=1, minute=30, second=0), args=[app])
        scheduler.start()
        atexit.register(lambda: scheduler.shutdown())

        websocket_listener = WebSocketListener(app)
        websocket_listener.start()
    else:
        logger.info("RUN_BACKGROUND_JOBS is disabled; skipping DB startup work (admin/seed/scheduler/websocket)")

    return app