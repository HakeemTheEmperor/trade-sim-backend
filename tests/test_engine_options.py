"""The connection pool follows the web server's thread count."""
import pytest

from app import engine_options


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in ("GUNICORN_THREADS", "DB_POOL_SIZE", "DB_MAX_OVERFLOW"):
        monkeypatch.delenv(name, raising=False)


def test_defaults_match_what_the_app_ran_with_before_they_were_configurable():
    # 4 threads, SQLAlchemy's usual pool of 5 plus 10 of overflow.
    assert engine_options() == {"pool_size": 5, "max_overflow": 10}


def test_pool_grows_with_the_thread_count(monkeypatch):
    monkeypatch.setenv("GUNICORN_THREADS", "16")
    assert engine_options()["pool_size"] == 16


def test_pool_never_drops_below_sqlalchemys_default(monkeypatch):
    monkeypatch.setenv("GUNICORN_THREADS", "2")
    assert engine_options()["pool_size"] == 5


def test_pool_and_overflow_can_be_set_explicitly(monkeypatch):
    monkeypatch.setenv("GUNICORN_THREADS", "16")
    monkeypatch.setenv("DB_POOL_SIZE", "8")
    monkeypatch.setenv("DB_MAX_OVERFLOW", "2")
    assert engine_options() == {"pool_size": 8, "max_overflow": 2}


def test_a_typo_falls_back_instead_of_crashing_the_app(monkeypatch):
    monkeypatch.setenv("GUNICORN_THREADS", "lots")
    monkeypatch.setenv("DB_MAX_OVERFLOW", "")
    assert engine_options() == {"pool_size": 5, "max_overflow": 10}
