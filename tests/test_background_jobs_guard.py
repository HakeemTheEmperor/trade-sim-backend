"""Background jobs must run in exactly one process, so unsafe settings are refused."""
import pytest

from app import background_jobs_enabled


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in ("RUN_BACKGROUND_JOBS", "GUNICORN_WORKERS"):
        monkeypatch.delenv(name, raising=False)


def test_jobs_run_by_default_with_the_default_single_worker():
    assert background_jobs_enabled() is True


def test_jobs_can_be_switched_off_for_a_web_only_service(monkeypatch):
    monkeypatch.setenv("RUN_BACKGROUND_JOBS", "false")
    monkeypatch.setenv("GUNICORN_WORKERS", "4")
    assert background_jobs_enabled() is False


def test_several_workers_with_jobs_enabled_is_refused(monkeypatch):
    monkeypatch.setenv("GUNICORN_WORKERS", "2")
    with pytest.raises(RuntimeError, match="RUN_BACKGROUND_JOBS=false"):
        background_jobs_enabled()


def test_the_refusal_applies_when_jobs_are_enabled_explicitly_too(monkeypatch):
    monkeypatch.setenv("RUN_BACKGROUND_JOBS", " True ")  # stray whitespace and case are tolerated
    monkeypatch.setenv("GUNICORN_WORKERS", "3")
    with pytest.raises(RuntimeError):
        background_jobs_enabled()


def test_one_worker_with_jobs_enabled_is_fine(monkeypatch):
    monkeypatch.setenv("GUNICORN_WORKERS", "1")
    assert background_jobs_enabled() is True


def test_an_unreadable_worker_count_falls_back_to_one(monkeypatch):
    monkeypatch.setenv("GUNICORN_WORKERS", "many")
    assert background_jobs_enabled() is True
