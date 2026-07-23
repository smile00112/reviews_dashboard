"""2GIS cabinet session endpoints — /api/scraper/2gis/* (feature 017)."""

import json

from app.models.enums import SessionStatus
from app.services.twogis_account_service import TwogisAccountService

TOKEN = "a4a92e92cfceb011112dff456130a4fbdf138d49"
PASTE = f"authorization: Bearer {TOKEN}"


def _point_session_at(db_session, tmp_path):
    service = TwogisAccountService(db_session)
    session = service.get_session_record()
    session.storage_state_path = str(tmp_path / "twogis-state.json")
    db_session.commit()
    return session


def test_import_writes_token_and_marks_valid(admin_client, db_session, tmp_path):
    session = _point_session_at(db_session, tmp_path)

    resp = admin_client.post("/api/scraper/2gis/session/import", json={"cookies": PASTE})

    assert resp.status_code == 200
    assert resp.json()["status"] == "valid"
    db_session.refresh(session)
    assert session.status == SessionStatus.valid
    state = json.loads((tmp_path / "twogis-state.json").read_text(encoding="utf-8"))
    assert state == {"access_token": TOKEN}


def test_import_accepts_a_bare_token(admin_client, db_session, tmp_path):
    _point_session_at(db_session, tmp_path)

    resp = admin_client.post("/api/scraper/2gis/session/import", json={"cookies": TOKEN})

    assert resp.status_code == 200


def test_import_rejects_paste_without_a_token(admin_client, db_session, tmp_path):
    _point_session_at(db_session, tmp_path)

    resp = admin_client.post("/api/scraper/2gis/session/import", json={"cookies": "locale: ru"})

    assert resp.status_code == 422
    assert not (tmp_path / "twogis-state.json").exists()


def test_import_never_echoes_the_token(admin_client, db_session, tmp_path):
    _point_session_at(db_session, tmp_path)

    resp = admin_client.post("/api/scraper/2gis/session/import", json={"cookies": PASTE})

    assert TOKEN not in resp.text


def test_import_requires_permission(client, db_session, tmp_path):
    _point_session_at(db_session, tmp_path)

    resp = client.post("/api/scraper/2gis/session/import", json={"cookies": PASTE})

    assert resp.status_code == 401


def test_get_session_reports_missing_before_import(admin_client, db_session, tmp_path):
    _point_session_at(db_session, tmp_path)

    resp = admin_client.get("/api/scraper/2gis/session")

    assert resp.status_code == 200
    assert resp.json()["status"] == "missing"


def test_check_without_token_is_missing_and_needs_no_network(admin_client, db_session, tmp_path):
    _point_session_at(db_session, tmp_path)

    # No storage-state file → the scraper short-circuits to "missing" without any HTTP call.
    resp = admin_client.post("/api/scraper/2gis/session/check")

    assert resp.status_code == 200
    assert resp.json()["status"] == "missing"


def test_check_requires_permission(client, db_session, tmp_path):
    _point_session_at(db_session, tmp_path)

    resp = client.post("/api/scraper/2gis/session/check")

    assert resp.status_code == 401
