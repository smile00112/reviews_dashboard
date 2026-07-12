"""Feature 010 / US1: batch-safe upsert — no lost inserts on mid-batch collision,
exact counters, idempotent re-scrape."""

from datetime import date

import pytest

from app.models.enums import ScrapeMode
from app.models.organization import Organization
from app.models.review import Review
from app.scraper.normalize import build_review_hash
from app.scraper.types import ParsedReview
from app.services.review_service import ReviewService


def _org(db):
    org = Organization(yandex_url="https://yandex.ru/maps/org/test/1/")
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


def _parsed(i: int) -> ParsedReview:
    return ParsedReview(
        author_name=f"Author {i}",
        rating=(i % 5) + 1,
        review_text=f"Review text number {i}",
        review_date_text=f"{i + 1} июня",
        review_date=date(2026, 6, min(i + 1, 28)),
        response_text=None,
        external_review_id=str(i),
    )


def test_mid_batch_collision_keeps_prior_inserts_and_exact_counters(db_session, monkeypatch):
    """A concurrent duplicate arriving between preload and flush must cost only
    that one row (resolved as update) — earlier inserts of the batch survive."""
    org = _org(db_session)
    service = ReviewService(db_session)
    batch = [_parsed(i) for i in range(5)]
    victim = batch[3]
    victim_hash = build_review_hash(
        victim.author_name, victim.rating, victim.review_date_text, victim.review_text
    )

    # Inject the duplicate BEFORE the victim's SAVEPOINT opens: the row then lives in
    # the outer transaction (like a concurrent scrape's commit) and survives the
    # savepoint rollback, while the service's own insert collides on the unique key.
    original_begin_nested = db_session.begin_nested
    calls = {"n": 0}
    injected = {"done": False}

    def sabotaging_begin_nested():
        calls["n"] += 1
        if calls["n"] == 4:  # 4th new review == batch[3] (batch order preserved)
            injected["done"] = True
            from sqlalchemy import text

            db_session.connection().execute(
                text(
                    "INSERT INTO reviews (id, organization_id, source, scrape_mode, rating,"
                    " review_text, content_hash, first_seen_at, last_seen_at, is_paid)"
                    " VALUES (:id, :org, 'yandex_maps', 'public', :rating, :text, :hash,"
                    " CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 0)"
                ),
                {
                    # Match the ORM's SQLite storage format (uuid.hex, 32 chars, no
                    # dashes); letters keep NUMERIC affinity from coercing to float.
                    "id": "aaaaaaaaaaaa4aaa8aaaaaaaaaaaaaaa",
                    "org": org.id.hex,
                    "rating": victim.rating,
                    "text": victim.review_text,
                    "hash": victim_hash,
                },
            )
        return original_begin_nested()

    monkeypatch.setattr(db_session, "begin_nested", sabotaging_begin_nested)

    seen, inserted, updated = service.upsert_reviews(org.id, batch, ScrapeMode.public)

    monkeypatch.undo()
    assert injected["done"], "sabotage hook never fired"
    assert seen == 5
    assert inserted == 4  # victim collided
    assert updated == 1  # ...and was resolved as an update
    total = db_session.query(Review).filter(Review.organization_id == org.id).count()
    assert total == 5  # 4 batch inserts + 1 injected row; nothing lost, no dupes


def test_counters_match_db_effects(db_session):
    org = _org(db_session)
    service = ReviewService(db_session)

    seen, inserted, updated = service.upsert_reviews(org.id, [_parsed(i) for i in range(7)], ScrapeMode.public)
    assert (seen, inserted, updated) == (7, 7, 0)
    assert db_session.query(Review).filter(Review.organization_id == org.id).count() == 7


def test_rescrape_is_idempotent(db_session):
    org = _org(db_session)
    service = ReviewService(db_session)
    batch = [_parsed(i) for i in range(4)]

    service.upsert_reviews(org.id, batch, ScrapeMode.public)
    seen, inserted, updated = service.upsert_reviews(org.id, batch, ScrapeMode.public)

    assert (seen, inserted, updated) == (4, 0, 4)
    assert db_session.query(Review).filter(Review.organization_id == org.id).count() == 4


def test_intra_batch_duplicate_counts_once(db_session):
    """Same review appearing twice in one scrape batch → one insert + one update."""
    org = _org(db_session)
    service = ReviewService(db_session)
    dup = _parsed(1)

    seen, inserted, updated = service.upsert_reviews(org.id, [dup, dup], ScrapeMode.public)

    assert (seen, inserted, updated) == (2, 1, 1)
    assert db_session.query(Review).filter(Review.organization_id == org.id).count() == 1
