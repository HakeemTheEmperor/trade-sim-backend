"""Test harness: a real Postgres, the real migrations, a clean database per test.

Postgres, not SQLite, because the behaviour worth testing (row locks via
``with_for_update``, ``ON CONFLICT`` upserts) does not exist on SQLite. A
SQLite run would pass without proving anything.

Start the database with:
    docker compose -f docker-compose.test.yml up -d --wait
or point TEST_DATABASE_URI at any Postgres whose database name ends in
``_test``.
"""
import os

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url

DEFAULT_TEST_DB_URI = "postgresql://test:test@localhost:5433/imockmarket_test"
TEST_DB_URI = os.getenv("TEST_DATABASE_URI", DEFAULT_TEST_DB_URI)

# The suite drops the whole schema, so refuse anything that is not plainly a
# test database. This is the only thing standing between a mistyped env var and
# wiping a dev (or production) database.
_db_name = make_url(TEST_DB_URI).database or ""
if not _db_name.endswith("_test"):
    raise RuntimeError(
        f"Refusing to run tests against database {_db_name!r}: "
        "its name must end in '_test'."
    )

# create_app() calls load_dotenv(), which never overrides variables that are
# already set, so assigning here beats whatever is in .env. Everything that
# changes behaviour is pinned so a developer's .env cannot skew the results.
os.environ.update({
    "SQLALCHEMY_DATABASE_URI": TEST_DB_URI,
    "RUN_BACKGROUND_JOBS": "false",  # no scheduler, websocket, poller or seeding
    "JWT_SECRET_KEY": "test-only-secret-key-that-is-long-enough-for-hs256",
    "JWT_COOKIE_SECURE": "False",
    "SWAGGER_URL": "/docs",
    "TRADE_HALF_SPREAD": "0.0005",
    "FX_SPREAD": "0.005",
    "LOG_LEVEL": "WARNING",
})

from app import create_app, db  # noqa: E402  (must follow the env setup above)
from app.utils import rate_limit  # noqa: E402

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIGRATIONS_DIR = os.path.join(BACKEND_DIR, "migrations")


@pytest.fixture(scope="session")
def app():
    from flask_migrate import upgrade

    app = create_app()
    app.config.update(TESTING=True)
    with app.app_context():
        # Start from nothing and build the schema the way production does, so
        # the suite also proves the migrations apply cleanly from empty.
        with db.engine.begin() as conn:
            conn.execute(text("DROP SCHEMA public CASCADE"))
            conn.execute(text("CREATE SCHEMA public"))
        upgrade(directory=MIGRATIONS_DIR)
    return app


@pytest.fixture(autouse=True)
def app_context(app):
    """Clean database and a live app context for every test.

    Truncated rather than rolled back: the concurrency tests need several
    threads to commit for real, which a wrapping transaction would hide.
    """
    with app.app_context():
        tables = ", ".join(f'"{t.name}"' for t in db.metadata.sorted_tables)
        db.session.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
        db.session.commit()
        rate_limit._hits.clear()
        yield
        db.session.remove()


@pytest.fixture
def client(app):
    return app.test_client()
