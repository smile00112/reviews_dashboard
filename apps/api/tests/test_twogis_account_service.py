"""TwogisAccountService — 2GIS cabinet token import + check (feature 017)."""

import json

from app.models.enums import SessionStatus
from app.scraper.twogis_account import extract_bearer_token
from app.services.twogis_account_service import TwogisAccountService

TOKEN = "a4a92e92cfceb011112dff456130a4fbdf138d49"
HEADER_LINE = f"Bearer {TOKEN}"


class _FakeScraper:
    """Stand-in for TwogisAccountScraper.check_session — no network."""

    def __init__(self, result):
        self.result = result
        self.checked_path = None

    def check_session(self, storage_state_path):
        self.checked_path = storage_state_path
        return self.result


def _service_at(db_session, tmp_path, scraper=None):
    service = TwogisAccountService(db_session, scraper=scraper)
    session = service.get_session_record()
    session.storage_state_path = str(tmp_path / "twogis-state.json")
    db_session.commit()
    return service, session


# --- token extraction ---------------------------------------------------------

def test_extract_token_from_bearer_line():
    assert extract_bearer_token(f"authorization: Bearer {TOKEN}") == TOKEN


def test_extract_token_from_bare_paste():
    assert extract_bearer_token(TOKEN) == TOKEN


def test_extract_token_from_full_headers_block():
    block = f"accept\napplication/json\nauthorization\nBearer {TOKEN}\nx-api-key\naccweb96f8"
    assert extract_bearer_token(block) == TOKEN


def test_extract_token_returns_none_when_absent():
    assert extract_bearer_token("accept: application/json\nlocale: ru") is None
    assert extract_bearer_token("   ") is None


# --- import -------------------------------------------------------------------

def test_import_writes_token_and_marks_valid(db_session, tmp_path):
    service, _ = _service_at(db_session, tmp_path)

    result = service.import_session_cookies(HEADER_LINE)

    assert result.status == SessionStatus.valid
    assert result.last_login_at is not None
    state = json.loads((tmp_path / "twogis-state.json").read_text(encoding="utf-8"))
    assert state == {"access_token": TOKEN}


def test_import_accepts_a_bare_token(db_session, tmp_path):
    service, _ = _service_at(db_session, tmp_path)

    result = service.import_session_cookies(TOKEN)

    assert result.status == SessionStatus.valid
    assert json.loads((tmp_path / "twogis-state.json").read_text(encoding="utf-8"))["access_token"] == TOKEN


def test_import_rejects_paste_without_a_token_and_writes_nothing(db_session, tmp_path):
    service, _ = _service_at(db_session, tmp_path)

    try:
        service.import_session_cookies("locale: ru\naccept: application/json")
        assert False, "expected ValueError"
    except ValueError:
        pass
    assert not (tmp_path / "twogis-state.json").exists()


# --- check --------------------------------------------------------------------

def test_check_maps_valid(db_session, tmp_path):
    scraper = _FakeScraper((SessionStatus.valid, "ok"))
    service, _ = _service_at(db_session, tmp_path, scraper)
    service.import_session_cookies(HEADER_LINE)

    result = service.check_session()

    assert result.status == SessionStatus.valid
    assert result.last_message == "ok"
    assert result.last_checked_at is not None
    assert scraper.checked_path == str(tmp_path / "twogis-state.json")


def test_check_maps_expired(db_session, tmp_path):
    scraper = _FakeScraper((SessionStatus.expired, "no longer accepted"))
    service, _ = _service_at(db_session, tmp_path, scraper)
    service.import_session_cookies(HEADER_LINE)

    assert service.check_session().status == SessionStatus.expired


def test_check_maps_needs_manual_action(db_session, tmp_path):
    scraper = _FakeScraper((SessionStatus.needs_manual_action, "unreachable"))
    service, _ = _service_at(db_session, tmp_path, scraper)

    result = service.check_session()

    assert result.status == SessionStatus.needs_manual_action
    assert result.last_message == "unreachable"


def test_status_falls_back_to_missing_when_state_file_gone(db_session, tmp_path):
    service, _ = _service_at(db_session, tmp_path)
    service.import_session_cookies(HEADER_LINE)
    (tmp_path / "twogis-state.json").unlink()

    assert service.get_session_status().status == SessionStatus.missing


def test_yandex_and_twogis_sessions_are_independent_rows(db_session, tmp_path):
    from app.services.scrape_service import ScrapeService

    twogis, _ = _service_at(db_session, tmp_path)
    twogis.import_session_cookies(HEADER_LINE)

    yandex_row = ScrapeService(db_session).get_session_record()
    twogis_row = twogis.get_session_record()

    assert yandex_row.provider == "yandex"
    assert twogis_row.provider == "2gis"
    assert yandex_row.id != twogis_row.id
