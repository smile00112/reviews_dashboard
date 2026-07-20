"""ScrapeService._request_code / submit_code: the DB-polling handoff between
the background login and the operator submitting a confirmation code
(Yandex password+confirmation-code login)."""

import pytest

from app.models.enums import SessionStatus
from app.services import scrape_service as module
from app.services.scrape_service import ScrapeService


def test_request_code_sets_awaiting_code_and_clears_any_stale_code(db_session):
    service = ScrapeService(db_session)
    session = service.get_session_record()
    session.pending_code = "stale"
    db_session.commit()

    # Force an immediate timeout so the test doesn't actually wait.
    from app.core.config import settings as app_settings

    original_timeout = app_settings.yandex_code_wait_timeout_seconds
    app_settings.yandex_code_wait_timeout_seconds = 0
    try:
        code = service._request_code()
    finally:
        app_settings.yandex_code_wait_timeout_seconds = original_timeout

    assert code is None
    session2 = service.get_session_record()
    assert session2.status == SessionStatus.awaiting_code
    assert session2.pending_code is None


def test_request_code_returns_code_once_submitted_mid_wait(db_session, monkeypatch):
    service = ScrapeService(db_session)
    calls = {"n": 0}

    def fake_sleep(seconds):
        calls["n"] += 1
        if calls["n"] == 1:
            # Simulate the operator's POST /session/code landing mid-wait.
            fresh = service.get_session_record()
            fresh.pending_code = "123456"
            db_session.commit()

    monkeypatch.setattr(module.time, "sleep", fake_sleep)

    code = service._request_code()

    assert code == "123456"
    assert calls["n"] == 1
    session = service.get_session_record()
    assert session.status == SessionStatus.awaiting_code
    assert session.pending_code is None


def test_request_code_times_out_returns_none(db_session, monkeypatch):
    from app.core.config import settings as app_settings

    monkeypatch.setattr(app_settings, "yandex_code_wait_timeout_seconds", 0.02)
    monkeypatch.setattr(app_settings, "yandex_code_poll_interval_seconds", 0.005)

    service = ScrapeService(db_session)
    code = service._request_code()

    assert code is None
    session = service.get_session_record()
    assert session.status == SessionStatus.awaiting_code
    assert session.pending_code is None


def test_submit_code_writes_pending_code_when_awaiting(db_session):
    service = ScrapeService(db_session)
    session = service.get_session_record()
    session.status = SessionStatus.awaiting_code
    db_session.commit()

    result = service.submit_code("654321")

    assert result.pending_code == "654321"
    session2 = service.get_session_record()
    assert session2.pending_code == "654321"


def test_submit_code_rejects_when_not_awaiting(db_session):
    service = ScrapeService(db_session)

    with pytest.raises(ValueError):
        service.submit_code("111111")
