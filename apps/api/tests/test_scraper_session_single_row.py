"""One scraper_sessions row per provider.

Without this invariant `_get_or_create_session_record()`'s unordered
`.first()` can resolve to a different row on each call — Postgres rewrites
an updated row to the end of the heap, so the request that marks the session
`pending`, the background task that terminalizes it, and the UI's
`GET /session` poll can each land on a different row. The observed symptom
is a login stuck on "Выполняется вход…" forever with no error anywhere.
"""

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.scraper_session import ScraperSession
from app.services.scrape_service import ScrapeService


def test_provider_is_unique(db_session):
    db_session.add(ScraperSession(provider="yandex", storage_state_path="/tmp/a.json"))
    db_session.commit()

    db_session.add(ScraperSession(provider="yandex", storage_state_path="/tmp/b.json"))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_get_or_create_never_adds_a_second_row(db_session):
    first = ScrapeService(db_session).get_session_record()
    second = ScrapeService(db_session).get_session_record()

    assert first.id == second.id
    assert db_session.query(ScraperSession).filter(ScraperSession.provider == "yandex").count() == 1


def test_marking_pending_does_not_orphan_the_row(db_session):
    """The exact stuck-login sequence: mark pending, then re-resolve the
    record the way the background task and the poll each do."""
    service = ScrapeService(db_session)
    pending = service.mark_session_pending()

    assert ScrapeService(db_session).get_session_record().id == pending.id
    assert db_session.query(ScraperSession).filter(ScraperSession.provider == "yandex").count() == 1
