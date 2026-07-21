"""Scraped business-reply date: persistence, edit-sync, and dedup independence.

response_date is the reply's real platform publication day (parsed from the source),
distinct from response_first_seen_at (our observation time). It is synced with
response_text on re-scrape and never feeds the content_hash.
"""

from datetime import date

from app.models.enums import ScrapeMode
from app.models.organization import Organization
from app.models.review import Review
from app.scraper.types import ParsedReview
from app.services.review_service import ReviewService


def _make_org(db_session):
    org = Organization(
        yandex_url="https://yandex.ru/maps/org/test/123/",
        normalized_url="https://yandex.ru/maps/org/test/123",
        preferred_scrape_mode=ScrapeMode.public,
    )
    db_session.add(org)
    db_session.commit()
    return org


def _only_review(db_session) -> Review:
    return db_session.query(Review).one()


def test_insert_persists_response_date(db_session):
    org = _make_org(db_session)
    service = ReviewService(db_session)
    reviews = [
        ParsedReview(
            author_name="Anna",
            rating=5,
            review_text="Great",
            review_date_text="1 Jan",
            response_text="Thank you!",
            response_date=date(2026, 2, 16),
        )
    ]

    service.upsert_reviews(org.id, reviews, ScrapeMode.public)

    review = _only_review(db_session)
    assert review.response_date == date(2026, 2, 16)


def test_insert_without_response_leaves_date_null(db_session):
    org = _make_org(db_session)
    service = ReviewService(db_session)
    reviews = [ParsedReview(author_name="Bob", rating=4, review_text="Nice", review_date_text="2 Jan")]

    service.upsert_reviews(org.id, reviews, ScrapeMode.public)

    assert _only_review(db_session).response_date is None


def test_response_date_set_when_reply_appears_later(db_session):
    org = _make_org(db_session)
    service = ReviewService(db_session)
    base = ParsedReview(author_name="Cara", rating=3, review_text="Ok", review_date_text="3 Jan")
    service.upsert_reviews(org.id, [base], ScrapeMode.public)
    assert _only_review(db_session).response_date is None

    with_response = ParsedReview(
        author_name="Cara",
        rating=3,
        review_text="Ok",
        review_date_text="3 Jan",
        response_text="We appreciate it",
        response_date=date(2026, 3, 1),
    )
    _, inserted, updated = service.upsert_reviews(org.id, [with_response], ScrapeMode.public)

    review = _only_review(db_session)
    assert inserted == 0 and updated == 1  # deduped update in place
    assert review.response_date == date(2026, 3, 1)


def test_response_date_synced_when_reply_edited(db_session):
    org = _make_org(db_session)
    service = ReviewService(db_session)
    first = ParsedReview(
        author_name="Dan",
        rating=2,
        review_text="Meh",
        review_date_text="4 Jan",
        response_text="Sorry",
        response_date=date(2026, 1, 10),
    )
    service.upsert_reviews(org.id, [first], ScrapeMode.public)
    assert _only_review(db_session).response_date == date(2026, 1, 10)

    # Business edits the reply on a later run: its platform date moved forward.
    edited = ParsedReview(
        author_name="Dan",
        rating=2,
        review_text="Meh",
        review_date_text="4 Jan",
        response_text="Sorry — fixed now",
        response_date=date(2026, 1, 20),
    )
    service.upsert_reviews(org.id, [edited], ScrapeMode.public)

    review = _only_review(db_session)
    assert review.response_text == "Sorry — fixed now"
    assert review.response_date == date(2026, 1, 20)  # synced, unlike response_first_seen_at


def test_response_date_does_not_affect_dedup(db_session):
    org = _make_org(db_session)
    service = ReviewService(db_session)
    a = ParsedReview(
        author_name="Eve", rating=5, review_text="Love it", review_date_text="5 Jan",
        response_text="Thanks!", response_date=date(2026, 1, 1),
    )
    b = ParsedReview(
        author_name="Eve", rating=5, review_text="Love it", review_date_text="5 Jan",
        response_text="Thanks!", response_date=date(2026, 6, 6),
    )
    service.upsert_reviews(org.id, [a], ScrapeMode.public)
    service.upsert_reviews(org.id, [b], ScrapeMode.public)

    # A different response_date never re-inserts: it is outside the content_hash.
    assert db_session.query(Review).count() == 1
    assert _only_review(db_session).response_date == date(2026, 6, 6)
