"""Per-run limit override: --all-reviews must be able to lift the settings cap.

The settings default (http_scrape_limit=150) silently truncated a 1110-review org to
150. Callers can now pass an explicit limit/max_pages; omitting them (None) keeps the
settings value, so the API path and every existing caller are unaffected.
"""

import math

from app.core.config import settings
from app.models.enums import ScrapeMode
from app.models.organization import Organization
from app.scraper.types import ParsedOrganization, ParsedReview, ScrapeResult
from app.services.scrape_service import ScrapeService
from app.scraper.yandex_http import YandexHttpScraper

URL = "https://yandex.ru/maps/org/test/123/reviews/"


def _page_html(review_ids: range) -> str:
    """A reviews page with one review block per id, matching the markup shape of
    tests/fixtures/yandex_http_page.html (what parse_reviews_from_html expects)."""
    blocks = "".join(
        f"""
        <div class="business-review-view">
          <div class="business-review-view__author">
            <div class="business-review-view__author-name">Автор {i}</div>
          </div>
          <div class="business-rating-badge-view__stars" aria-label="Оценка 5 Из 5"></div>
          <span class="business-review-view__body-text">Отзыв номер {i}</span>
          <span class="business-review-view__date">2 мая 2024</span>
        </div>
        """
        for i in review_ids
    )
    return f'<html><body><h1>Кафе Пример</h1>{blocks}</body></html>'


def test_explicit_limit_caps_collection(monkeypatch):
    monkeypatch.setattr(settings, "http_scrape_limit", 150)
    scraper = YandexHttpScraper()
    monkeypatch.setattr(YandexHttpScraper, "_fetch", lambda self, url: _page_html(range(20)))

    result = scraper.scrape(URL, limit=5)

    assert len(result.reviews) == 5


def test_omitted_limit_falls_back_to_settings(monkeypatch):
    monkeypatch.setattr(settings, "http_scrape_limit", 3)
    scraper = YandexHttpScraper()
    monkeypatch.setattr(YandexHttpScraper, "_fetch", lambda self, url: _page_html(range(20)))

    result = scraper.scrape(URL)

    assert len(result.reviews) == 3


def test_infinite_limit_collects_every_review(monkeypatch):
    monkeypatch.setattr(settings, "http_scrape_limit", 5)
    scraper = YandexHttpScraper()
    monkeypatch.setattr(YandexHttpScraper, "_fetch", lambda self, url: _page_html(range(20)))

    result = scraper.scrape(URL, limit=math.inf)

    # All 20 distinct reviews on the page, despite the settings cap of 5.
    assert len(result.reviews) == 20


def test_max_pages_override_controls_pagination(monkeypatch):
    monkeypatch.setattr(settings, "http_scrape_max_pages", 5)
    monkeypatch.setattr(settings, "http_scrape_delay_seconds", 0)
    scraper = YandexHttpScraper()

    pages_fetched = []

    def fake_fetch(self, url):
        pages_fetched.append(url)
        # Distinct reviews per page so pagination never stops early.
        page_no = len(pages_fetched)
        return _page_html(range(page_no * 100, page_no * 100 + 3))

    monkeypatch.setattr(YandexHttpScraper, "_fetch", fake_fetch)

    scraper.scrape(URL, limit=math.inf, max_pages=2)

    assert len(pages_fetched) == 2


def test_twogis_explicit_limit_caps_collection(monkeypatch):
    """2GIS paginates by offset rather than page number, but honours the same
    limit override so --all-reviews works across platforms."""
    from app.scraper.twogis_api import CATALOG_URL, TwogisApiScraper

    monkeypatch.setattr(settings, "twogis_review_limit", 150)
    monkeypatch.setattr(settings, "twogis_page_size", 2)
    monkeypatch.setattr(settings, "twogis_request_delay_seconds", 0)

    catalog = {
        "meta": {"code": 200},
        "result": {"items": [{"name": "Суши", "org": {"id": "1"}, "reviews": {"general_rating": 4.5}}]},
    }

    def fake_get_json(self, url, params):
        if url == CATALOG_URL:
            return catalog, None
        offset = params["offset"]
        return {
            # next_link present on every page: pagination must be stopped by the
            # limit, not by the API running out of pages.
            "meta": {"next_link": "https://example/next"},
            "reviews": [
                {
                    "id": f"r{offset + i}",
                    "user": {"name": f"Автор {offset + i}"},
                    "rating": 5,
                    "text": f"Отзыв {offset + i}",
                    "date_created": "2026-07-01 10:00:00",
                }
                for i in range(params["limit"])
            ],
        }, None

    monkeypatch.setattr(TwogisApiScraper, "_get_json", fake_get_json)

    result = TwogisApiScraper().scrape("https://2gis.ru/achinsk/firm/123", limit=5)

    assert len(result.reviews) == 5


class _RecordingScraper:
    def __init__(self):
        self.kwargs = None

    def scrape(self, url, **kwargs):
        self.kwargs = kwargs
        return ScrapeResult(
            organization=ParsedOrganization(name="Кафе", rating=4.0, review_count=1),
            reviews=[ParsedReview(author_name="Анна", rating=5, review_text="Вкусно", review_date_text="1 мая")],
        )


def test_service_passes_overrides_through_to_the_scraper(db_session):
    org = Organization(yandex_url=URL, preferred_scrape_mode=ScrapeMode.public_http)
    db_session.add(org)
    db_session.commit()

    http = _RecordingScraper()
    service = ScrapeService(db_session, http_scraper=http)

    run = service.create_run(org.id, ScrapeMode.public_http)
    service.execute_run(run.id, limit=math.inf, max_pages=100)

    assert http.kwargs == {"limit": math.inf, "max_pages": 100}


def test_service_without_overrides_passes_nothing(db_session):
    org = Organization(yandex_url=URL, preferred_scrape_mode=ScrapeMode.public_http)
    db_session.add(org)
    db_session.commit()

    http = _RecordingScraper()
    service = ScrapeService(db_session, http_scraper=http)

    run = service.create_run(org.id, ScrapeMode.public_http)
    service.execute_run(run.id)

    # Existing callers (the API) must reach the scraper exactly as before.
    assert http.kwargs == {}
