from app.models.enums import ScrapeMode
from app.models.organization import Organization
from app.models.review import Review
from app.scraper.types import ParsedOrganization, ParsedReview, ScrapeResult
from app.services.scrape_service import ScrapeService


class FakeScraper:
    def __init__(self, result):
        self._result = result
        self.calls = 0

    def scrape(self, url):
        self.calls += 1
        return self._result


def _org(db):
    org = Organization(
        yandex_url="https://yandex.ru/maps/org/test/123/reviews/",
        normalized_url="https://yandex.ru/maps/org/test/123",
        preferred_scrape_mode=ScrapeMode.public,
    )
    db.add(org)
    db.commit()
    return org


def _result():
    return ScrapeResult(
        organization=ParsedOrganization(name="Кафе Пример", rating=4.3, review_count=2),
        reviews=[
            ParsedReview(author_name="Анна", rating=5, review_text="Очень вкусно", review_date_text="1 мая"),
            ParsedReview(author_name="Иван", rating=2, review_text="Грязно и долго", review_date_text="2 мая"),
        ],
    )


def test_public_http_routes_to_http_scraper(db_session):
    org = _org(db_session)
    http = FakeScraper(_result())
    public = FakeScraper(_result())
    service = ScrapeService(db_session, public_scraper=public, http_scraper=http)

    run = service.create_run(org.id, ScrapeMode.public_http)
    service.execute_run(run.id)

    # HTTP scraper used, Playwright public scraper untouched.
    assert http.calls == 1
    assert public.calls == 0

    run = service.get_run(run.id)
    assert run.status.value == "success"
    assert run.reviews_inserted == 2

    stored = db_session.query(Review).all()
    assert len(stored) == 2
    assert all(r.scrape_mode == ScrapeMode.public_http for r in stored)
    # Analytics (feature 002) ran on HTTP-scraped reviews too.
    assert all(r.sentiment is not None for r in stored)


def test_public_http_second_run_dedups(db_session):
    org = _org(db_session)
    http = FakeScraper(_result())
    service = ScrapeService(db_session, http_scraper=http)

    first = service.create_run(org.id, ScrapeMode.public_http)
    service.execute_run(first.id)
    second = service.create_run(org.id, ScrapeMode.public_http)
    service.execute_run(second.id)

    run = service.get_run(second.id)
    assert run.reviews_inserted == 0
    assert run.reviews_updated == 2
    assert db_session.query(Review).count() == 2


def test_public_mode_still_uses_playwright_scraper(db_session):
    org = _org(db_session)
    http = FakeScraper(_result())
    public = FakeScraper(_result())
    service = ScrapeService(db_session, public_scraper=public, http_scraper=http)

    run = service.create_run(org.id, ScrapeMode.public)
    service.execute_run(run.id)

    assert public.calls == 1
    assert http.calls == 0


def test_scrapeops_mode_routes_to_scrapeops_scraper(db_session):
    org = _org(db_session)
    scrapeops = FakeScraper(_result())
    public = FakeScraper(_result())
    http = FakeScraper(_result())
    service = ScrapeService(db_session, public_scraper=public, http_scraper=http, scrapeops_scraper=scrapeops)

    run = service.create_run(org.id, ScrapeMode.scrapeops)
    service.execute_run(run.id)

    assert scrapeops.calls == 1
    assert public.calls == 0
    assert http.calls == 0

    run = service.get_run(run.id)
    assert run.status.value == "success"
    assert run.reviews_inserted == 2
