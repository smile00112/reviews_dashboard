"""Feature 010 / US3: session login/check schedule background work and expose
the pending state; 202 responses are truthful."""

import pytest

from app.models.enums import SessionStatus
from app.models.scraper_session import ScraperSession
from app.services.scrape_service import ScrapeService


@pytest.fixture()
def _no_real_background(monkeypatch, db_session):
    """Capture scheduled background fns instead of running Playwright; run them
    against the test session on demand."""
    from app.api import scraper_sessions as module

    calls = {"login": 0, "check": 0}

    def fake_login_bg():
        calls["login"] += 1
        service = ScrapeService(db_session)
        service.auth_scraper = _StubAuth()
        service.login_operator()

    def fake_check_bg():
        calls["check"] += 1
        service = ScrapeService(db_session)
        service.auth_scraper = _StubAuth()
        service.check_session()

    monkeypatch.setattr(module, "_run_login_background", fake_login_bg)
    monkeypatch.setattr(module, "_run_check_background", fake_check_bg)
    return calls


class _StubAuth:
    def login(self, login, password, path):
        return SessionStatus.valid, "ok"

    def check_session(self, path):
        return SessionStatus.valid


def test_login_returns_pending_immediately_then_terminal(admin_client, _no_real_background, db_session):
    resp = admin_client.post("/api/scraper/yandex/login")
    assert resp.status_code == 202
    assert resp.json()["status"] == "pending"

    # TestClient runs BackgroundTasks after the response; ours was monkeypatched
    # to execute synchronously against the test DB.
    assert _no_real_background["login"] == 1
    session = db_session.query(ScraperSession).first()
    db_session.refresh(session)
    assert session.status == SessionStatus.valid


def test_second_login_while_pending_does_not_reschedule(admin_client, _no_real_background, db_session, monkeypatch):
    # Freeze the background fn to a no-op so the session STAYS pending.
    from app.api import scraper_sessions as module

    noop_calls = {"n": 0}

    def noop():
        noop_calls["n"] += 1

    monkeypatch.setattr(module, "_run_login_background", noop)

    first = admin_client.post("/api/scraper/yandex/login")
    assert first.json()["status"] == "pending"
    assert noop_calls["n"] == 1

    second = admin_client.post("/api/scraper/yandex/login")
    assert second.status_code == 202
    assert second.json()["status"] == "pending"
    assert "already in progress" in second.json()["message"]
    assert noop_calls["n"] == 1  # not scheduled again


def test_check_session_is_async_and_pending(admin_client, _no_real_background, db_session):
    resp = admin_client.post("/api/scraper/yandex/session/check")
    assert resp.status_code == 202
    assert resp.json()["status"] == "pending"
    assert _no_real_background["check"] == 1
    session = db_session.query(ScraperSession).first()
    db_session.refresh(session)
    assert session.status == SessionStatus.valid


def test_get_session_does_not_clobber_pending(client, db_session, tmp_path, monkeypatch):
    # Existing non-empty storage-state file would normally flip status to valid.
    state = tmp_path / "state.json"
    state.write_text("{}", encoding="utf-8")

    service = ScrapeService(db_session)
    session = service.get_session_record()
    session.storage_state_path = str(state)
    session.status = SessionStatus.pending
    db_session.commit()

    resp = client.get("/api/scraper/yandex/session")
    assert resp.status_code == 200
    assert resp.json()["status"] == "pending"


def test_login_exception_reaches_terminal_state(db_session):
    class _BoomAuth:
        def login(self, *a):
            raise RuntimeError("browser died")

    service = ScrapeService(db_session)
    service.auth_scraper = _BoomAuth()
    service.mark_session_pending()
    status, message = service.login_operator()
    assert status == SessionStatus.needs_manual_action
    session = db_session.query(ScraperSession).first()
    assert session.status == SessionStatus.needs_manual_action
