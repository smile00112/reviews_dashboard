from app.models.enums import ScrapeMode
from app.models.organization import Organization
from app.models.review import Review
from app.scraper.types import ParsedReview
from app.services.review_service import ReviewService


def test_duplicate_reviews_not_inserted_twice(db_session):
    org = Organization(
        yandex_url="https://yandex.ru/maps/org/test/123/",
        normalized_url="https://yandex.ru/maps/org/test/123",
        preferred_scrape_mode=ScrapeMode.public,
    )
    db_session.add(org)
    db_session.commit()

    service = ReviewService(db_session)
    reviews = [
        ParsedReview(author_name="Anna", rating=5, review_text="Great place", review_date_text="1 Jan"),
    ]

    seen1, inserted1, _ = service.upsert_reviews(org.id, reviews, ScrapeMode.public)
    seen2, inserted2, updated2 = service.upsert_reviews(org.id, reviews, ScrapeMode.public)

    assert seen1 == 1 and inserted1 == 1
    assert seen2 == 1 and inserted2 == 0 and updated2 == 1
    assert db_session.query(Review).count() == 1
