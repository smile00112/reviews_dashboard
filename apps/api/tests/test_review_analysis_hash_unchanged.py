"""Dedup contract regression: analysis must never change content_hash."""

from app.models.enums import ScrapeMode
from app.models.organization import Organization
from app.models.review import Review
from app.scraper.types import ParsedReview
from app.services.analysis_service import AnalysisService
from app.services.review_service import ReviewService


def _make_org(db):
    org = Organization(
        yandex_url="https://yandex.ru/maps/org/test/123/",
        normalized_url="https://yandex.ru/maps/org/test/123",
        preferred_scrape_mode=ScrapeMode.public,
    )
    db.add(org)
    db.commit()
    return org


def test_analysis_fields_populated_on_insert(db_session):
    org = _make_org(db_session)
    reviews = [
        ParsedReview(author_name="Anna", rating=5, review_text="Очень вкусно и чисто", review_date_text="1 Jan"),
        ParsedReview(author_name="Ivan", rating=2, review_text="Грязно и долго ждать", review_date_text="2 Jan"),
    ]
    ReviewService(db_session).upsert_reviews(org.id, reviews, ScrapeMode.public)

    stored = db_session.query(Review).order_by(Review.rating).all()
    for r in stored:
        assert r.sentiment in {"positive", "negative", "neutral"}
        assert r.analyzed_at is not None
        assert r.problems is not None  # [] or list, never None after analysis


def test_content_hash_unchanged_after_reanalysis(db_session):
    org = _make_org(db_session)
    reviews = [
        ParsedReview(author_name="Anna", rating=5, review_text="Ужасно невкусно", review_date_text="1 Jan"),
    ]
    ReviewService(db_session).upsert_reviews(org.id, reviews, ScrapeMode.public)

    before = db_session.query(Review).one().content_hash

    # Re-run analysis (backfill) over the same data.
    AnalysisService(db_session).analyze_organization(org.id)

    after = db_session.query(Review).one().content_hash
    assert before == after


def test_reanalysis_is_idempotent(db_session):
    org = _make_org(db_session)
    reviews = [ParsedReview(author_name="A", rating=1, review_text="Кошмар, грязно", review_date_text="x")]
    ReviewService(db_session).upsert_reviews(org.id, reviews, ScrapeMode.public)

    svc = AnalysisService(db_session)
    svc.analyze_organization(org.id)
    first = db_session.query(Review).one()
    sentiment_1, problems_1 = first.sentiment, first.problems

    svc.analyze_organization(org.id)
    second = db_session.query(Review).one()
    assert second.sentiment == sentiment_1
    assert second.problems == problems_1
