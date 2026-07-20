"""ScraperSession gains an awaiting_code status + pending_code column
(Yandex password+confirmation-code login feature)."""

from app.models.enums import SessionStatus
from app.models.scraper_session import ScraperSession


def test_scraper_session_defaults_pending_code_to_none(db_session):
    session = ScraperSession(provider="yandex", storage_state_path="/tmp/state.json")
    db_session.add(session)
    db_session.commit()
    db_session.refresh(session)

    assert session.pending_code is None


def test_scraper_session_can_be_set_to_awaiting_code_with_a_pending_code(db_session):
    session = ScraperSession(provider="yandex", storage_state_path="/tmp/state.json")
    db_session.add(session)
    db_session.commit()

    session.status = SessionStatus.awaiting_code
    session.pending_code = "123456"
    db_session.commit()
    db_session.refresh(session)

    assert session.status == SessionStatus.awaiting_code
    assert session.pending_code == "123456"
