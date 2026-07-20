"""POST /api/scraper/yandex/session/import — manual cookie handover."""

from app.models.enums import SessionStatus
from app.services.scrape_service import ScrapeService

SESSION_VALUE = "3:1234567890.5.0.1234567890:abcdef:1.1|123456789.0.2|:xyz"
HEADER = f"Session_id={SESSION_VALUE}; yandexuid=42"


def _point_session_at(db_session, tmp_path):
    service = ScrapeService(db_session)
    session = service.get_session_record()
    session.storage_state_path = str(tmp_path / "state.json")
    db_session.commit()
    return session


def test_import_writes_the_storage_state_and_marks_the_session_valid(admin_client, db_session, tmp_path):
    import json

    session = _point_session_at(db_session, tmp_path)

    resp = admin_client.post("/api/scraper/yandex/session/import", json={"cookies": HEADER})

    assert resp.status_code == 200
    assert resp.json()["status"] == "valid"

    db_session.refresh(session)
    assert session.status == SessionStatus.valid
    assert session.last_login_at is not None

    state = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    assert [c["name"] for c in state["cookies"]] == ["Session_id", "yandexuid"]


def test_import_rejects_cookies_without_a_session_id(admin_client, db_session, tmp_path):
    _point_session_at(db_session, tmp_path)

    resp = admin_client.post("/api/scraper/yandex/session/import", json={"cookies": "yandexuid=42"})

    assert resp.status_code == 422
    assert "Session_id" in resp.text
    assert not (tmp_path / "state.json").exists(), "a rejected import must not leave a half-written state"


def test_import_never_echoes_the_cookie_values(admin_client, db_session, tmp_path):
    _point_session_at(db_session, tmp_path)

    resp = admin_client.post("/api/scraper/yandex/session/import", json={"cookies": HEADER})

    assert SESSION_VALUE not in resp.text


def test_import_requires_admin(client, db_session, tmp_path):
    _point_session_at(db_session, tmp_path)

    resp = client.post("/api/scraper/yandex/session/import", json={"cookies": HEADER})

    assert resp.status_code == 401
