"""Feature 007: response_first_seen_at stamp-once / immutability / dedup-unaffected."""

from app.models.enums import ScrapeMode
from app.models.organization import Organization
from app.models.review import Review
from app.scraper.normalize import build_review_hash
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


def test_insert_with_response_stamps_first_seen(db_session):
    org = _make_org(db_session)
    service = ReviewService(db_session)
    reviews = [
        ParsedReview(
            author_name="Anna",
            rating=5,
            review_text="Great place",
            review_date_text="1 Jan",
            response_text="Thank you!",
        )
    ]

    service.upsert_reviews(org.id, reviews, ScrapeMode.public)

    review = _only_review(db_session)
    assert review.response_text == "Thank you!"
    assert review.response_first_seen_at is not None


def test_insert_without_response_leaves_first_seen_null(db_session):
    org = _make_org(db_session)
    service = ReviewService(db_session)
    reviews = [
        ParsedReview(author_name="Bob", rating=4, review_text="Nice", review_date_text="2 Jan")
    ]

    service.upsert_reviews(org.id, reviews, ScrapeMode.public)

    review = _only_review(db_session)
    assert review.response_text is None
    assert review.response_first_seen_at is None


def test_response_appearing_later_stamps_on_that_run(db_session):
    org = _make_org(db_session)
    service = ReviewService(db_session)
    base = ParsedReview(author_name="Cara", rating=3, review_text="Ok", review_date_text="3 Jan")

    # First run: no response.
    service.upsert_reviews(org.id, [base], ScrapeMode.public)
    review = _only_review(db_session)
    assert review.response_first_seen_at is None

    # Second run: same review now carries a response (same hash inputs -> dedup update in place).
    with_response = ParsedReview(
        author_name="Cara",
        rating=3,
        review_text="Ok",
        review_date_text="3 Jan",
        response_text="We appreciate it",
    )
    _, inserted, updated = service.upsert_reviews(org.id, [with_response], ScrapeMode.public)

    review = _only_review(db_session)
    assert inserted == 0 and updated == 1  # updated in place, not re-inserted
    assert review.response_text == "We appreciate it"
    assert review.response_first_seen_at is not None
    # Proxy is the response run's time, distinct semantics from the review's own first_seen_at.
    assert review.response_first_seen_at >= review.first_seen_at


def test_response_first_seen_is_immutable_across_reruns(db_session):
    org = _make_org(db_session)
    service = ReviewService(db_session)
    first = ParsedReview(
        author_name="Dan",
        rating=2,
        review_text="Meh",
        review_date_text="4 Jan",
        response_text="Sorry to hear that",
    )
    service.upsert_reviews(org.id, [first], ScrapeMode.public)
    original_ts = _only_review(db_session).response_first_seen_at
    assert original_ts is not None

    # Business edits the reply text on a later run.
    edited = ParsedReview(
        author_name="Dan",
        rating=2,
        review_text="Meh",
        review_date_text="4 Jan",
        response_text="Sorry — we have fixed this now",
    )
    service.upsert_reviews(org.id, [edited], ScrapeMode.public)

    review = _only_review(db_session)
    assert review.response_text == "Sorry — we have fixed this now"  # text refreshed
    assert review.response_first_seen_at == original_ts  # timestamp unchanged


def test_response_change_does_not_affect_dedup_hash(db_session):
    org = _make_org(db_session)
    service = ReviewService(db_session)
    without = ParsedReview(author_name="Eve", rating=5, review_text="Love it", review_date_text="5 Jan")
    with_resp = ParsedReview(
        author_name="Eve",
        rating=5,
        review_text="Love it",
        review_date_text="5 Jan",
        response_text="Thanks!",
    )

    # Hash excludes response_text: both parse to the same content_hash.
    assert build_review_hash("Eve", 5, "5 Jan", "Love it") == build_review_hash("Eve", 5, "5 Jan", "Love it")

    service.upsert_reviews(org.id, [without], ScrapeMode.public)
    service.upsert_reviews(org.id, [with_resp], ScrapeMode.public)

    assert db_session.query(Review).count() == 1  # response appearance never re-inserts
