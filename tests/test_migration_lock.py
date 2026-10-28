"""Two services starting together must not both apply the same migration.

bootstrap.sh runs `flask db upgrade` on every start. With a web service and a
worker service deploying at once, two upgrades hit an empty or out-of-date
database simultaneously. migrations/env.py takes a Postgres advisory lock so the
second waits and then finds nothing left to do.

Runs the real CLI in two real processes against a scratch database, because the
race is between processes and cannot be reproduced inside one.
"""
import os
import subprocess
import sys

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from tests.conftest import BACKEND_DIR, TEST_DB_URI

SCRATCH = "imockmarket_lock_test"  # ends in _test, like every database the suite touches


def run_upgrade(uri):
    env = dict(os.environ,
               FLASK_APP="app.index", SQLALCHEMY_DATABASE_URI=uri, RUN_BACKGROUND_JOBS="false",
               JWT_SECRET_KEY="test-only-secret-key-that-is-long-enough-for-hs256", SWAGGER_URL="/docs")
    return subprocess.Popen(
        [sys.executable, "-m", "flask", "db", "upgrade"],
        cwd=BACKEND_DIR, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )


@pytest.fixture
def scratch_database():
    server = make_url(TEST_DB_URI)
    admin = create_engine(server.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{SCRATCH}"'))
        conn.execute(text(f'CREATE DATABASE "{SCRATCH}"'))
    yield server.set(database=SCRATCH).render_as_string(hide_password=False)
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{SCRATCH}" WITH (FORCE)'))
    admin.dispose()


def test_concurrent_upgrades_of_an_empty_database_both_succeed(scratch_database):
    processes = [run_upgrade(scratch_database) for _ in range(3)]
    outputs = [p.communicate(timeout=180)[0] for p in processes]

    for process, output in zip(processes, outputs):
        assert process.returncode == 0, output[-1500:]

    engine = create_engine(scratch_database)
    with engine.connect() as conn:
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalars().all()
    engine.dispose()
    assert len(version) == 1  # one head, recorded once
