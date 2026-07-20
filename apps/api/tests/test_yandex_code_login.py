"""POST /api/scraper/yandex/session/code — the operator's confirmation-code
submission endpoint (Yandex password+confirmation-code login)."""

from app.models.enums import SessionStatus
from app.services.scrape_service import ScrapeService


def test_submit_code_succeeds_when_awaiting_code(admin_client, db_session):
    service = ScrapeService(db_session)
    session = service.get_session_record()
    session.status = SessionStatus.awaiting_code
    db_session.commit()

    resp = admin_client.post("/api/scraper/yandex/session/code", json={"code": "123456"})

    assert resp.status_code == 200
    assert resp.json()["status"] == "awaiting_code"
    db_session.refresh(session)
    assert session.pending_code == "123456"


def test_submit_code_rejects_when_no_login_in_progress(admin_client, db_session):
    resp = admin_client.post("/api/scraper/yandex/session/code", json={"code": "123456"})
    assert resp.status_code == 409


def test_submit_code_rejects_non_digit_code(admin_client, db_session):
    service = ScrapeService(db_session)
    session = service.get_session_record()
    session.status = SessionStatus.awaiting_code
    db_session.commit()

    resp = admin_client.post("/api/scraper/yandex/session/code", json={"code": "abc123"})
    assert resp.status_code == 422


def test_submit_code_never_echoes_pending_code(admin_client, db_session):
    service = ScrapeService(db_session)
    session = service.get_session_record()
    session.status = SessionStatus.awaiting_code
    db_session.commit()

    resp = admin_client.post("/api/scraper/yandex/session/code", json={"code": "123456"})
    assert "123456" not in resp.text
