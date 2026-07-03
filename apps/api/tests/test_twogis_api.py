"""Tests for the 2GIS reviews API scraper (twogis_api mode, feature 006)."""

from app.models.enums import ReviewPlatform, ScrapeMode
from app.models.organization import Organization
from app.models.review import Review
from app.scraper.twogis_api import CATALOG_URL, TwogisApiScraper
from app.scraper.types import ParsedOrganization, ParsedReview, ScrapeResult
from app.services.scrape_service import ScrapeService

FULL_URL = "https://2gis.ru/achinsk/firm/70000001027742089/tab/reviews"

CATALOG = {
    "meta": {"code": 200},
    "result": {
        "items": [
            {
                "name": "Суши мастер, служба доставки",
                "org": {"id": "70000001027742088"},
                "reviews": {
                    "org_rating": 4.2,
                    "org_review_count": 654,
                    "general_rating": 4.7,
                    "general_review_count": 294,
                },
            }
        ]
    },
}

REVIEWS_PAGE = {
    "meta": {},  # no next_link → single page
    "reviews": [
        {
            "id": "r1",
            "user": {"name": "Ната Филипова"},
            "rating": 5,
            "text": "Очень вкусно",
            "date_created": "2026-07-01 10:00:00",
            "official_answer": {"text": "Спасибо за отзыв!"},
        },
        {
            "id": "r2",
            "user": {"name": "Жанна Гаврилова"},
            "rating": 4,
            "text": "Нормально",
            "date_created": "2026-06-28 09:00:00",
        },
    ],
}


def _fake_get_json(catalog=CATALOG, reviews=REVIEWS_PAGE):
    def _inner(self, url, params):
        if url == CATALOG_URL:
            return catalog, None
        return reviews, None

    return _inner


# --- mapping ---------------------------------------------------------------


def test_map_review_maps_all_fields():
    pr = TwogisApiScraper._map_review(REVIEWS_PAGE["reviews"][0])
    assert pr.author_name == "Ната Филипова"
    assert pr.rating == 5
    assert pr.review_text == "Очень вкусно"
    # date_created is used verbatim so the content_hash stays stable across re-scrapes.
    assert pr.review_date_text == "2026-07-01 10:00:00"
    assert pr.review_date is not None and pr.review_date.isoformat() == "2026-07-01"
    assert pr.response_text == "Спасибо за отзыв!"
    assert pr.external_review_id == "r1"


def test_map_review_degrades_safely_on_missing_fields():
    pr = TwogisApiScraper._map_review(
        {"user": {}, "rating": None, "text": None, "date_created": "", "official_answer": None}
    )
    assert pr.rating == 0
    assert pr.review_text == ""
    assert pr.review_date_text is None
    assert pr.review_date is None
    assert pr.response_text is None


# --- firm id resolution ----------------------------------------------------


def test_resolve_firm_id_from_full_url_no_network(monkeypatch):
    def boom(self, url):
        raise AssertionError("proxy must not be called for a full /firm/ URL")

    monkeypatch.setattr(TwogisApiScraper, "_proxy_html", boom)
    firm_id, challenge = TwogisApiScraper()._resolve_firm_id(FULL_URL)
    assert firm_id == "70000001027742089"
    assert challenge is None


def test_resolve_firm_id_short_link_picks_dominant_id(monkeypatch):
    html = '<a href="/firm/999">a</a><a href="/firm/999">b</a><a href="/firm/111">c</a>'
    monkeypatch.setattr(TwogisApiScraper, "_proxy_html", lambda self, url: (html, None))
    firm_id, challenge = TwogisApiScraper()._resolve_firm_id("https://go.2gis.com/xbrHO")
    assert firm_id == "999"
    assert challenge is None


def test_short_link_without_proxy_key_needs_manual_action(monkeypatch):
    monkeypatch.setattr("app.scraper.twogis_api.settings.scrapeops_api_key", "")
    result = TwogisApiScraper().scrape("https://go.2gis.com/xbrHO")
    assert result.needs_manual_action is True
    assert result.error_code == "twogis_no_proxy_key"
    assert result.reviews == []


# --- scrape end to end (mocked transport) ----------------------------------


def test_scrape_collects_and_maps_reviews(monkeypatch):
    monkeypatch.setattr(TwogisApiScraper, "_get_json", _fake_get_json())
    result = TwogisApiScraper().scrape(FULL_URL)
    assert result.error_code is None
    assert result.needs_manual_action is False
    assert result.organization.name == "Суши мастер, служба доставки"
    assert result.organization.rating == 4.2
    assert result.organization.review_count == 654
    assert len(result.reviews) == 2
    assert result.reviews[0].author_name == "Ната Филипова"


def test_blocked_catalog_key_is_needs_manual_action(monkeypatch):
    blocked = {"meta": {"code": 403, "error": {"type": "apiKeyIsBlocked", "message": "blocked"}}}
    monkeypatch.setattr(TwogisApiScraper, "_get_json", lambda self, url, params: (blocked, None))
    result = TwogisApiScraper().scrape(FULL_URL)
    assert result.needs_manual_action is True
    assert result.error_code == "twogis_key_blocked"
    assert result.reviews == []


def test_firm_not_found_is_error(monkeypatch):
    empty = {"meta": {"code": 200}, "result": {"items": []}}
    monkeypatch.setattr(TwogisApiScraper, "_get_json", lambda self, url, params: (empty, None))
    result = TwogisApiScraper().scrape(FULL_URL)
    assert result.needs_manual_action is False
    assert result.error_code == "twogis_firm_not_found"


def test_redact_strips_scrapeops_key(monkeypatch):
    monkeypatch.setattr("app.scraper.twogis_api.settings.scrapeops_api_key", "SECRETKEY")
    redacted = TwogisApiScraper._redact("proxy.scrapeops.io/v1/?api_key=SECRETKEY&url=x")
    assert "SECRETKEY" not in redacted


# --- persistence / routing (db-backed) -------------------------------------


class _FakeScraper:
    def __init__(self, result):
        self._result = result
        self.calls = 0

    def scrape(self, url):
        self.calls += 1
        return self._result


def _twogis_org(db):
    org = Organization(
        yandex_url="https://2gis.ru/achinsk/firm/70000001027742089",
        normalized_url="https://2gis.ru/achinsk/firm/70000001027742089",
        preferred_scrape_mode=ScrapeMode.twogis_api,
    )
    db.add(org)
    db.commit()
    return org


def _result():
    return ScrapeResult(
        organization=ParsedOrganization(name="Суши мастер", rating=4.2, review_count=654),
        reviews=[
            ParsedReview(
                author_name="Ната Филипова",
                rating=5,
                review_text="Очень вкусно",
                review_date_text="2026-07-01 10:00:00",
            ),
            ParsedReview(
                author_name="Жанна Гаврилова",
                rating=4,
                review_text="Нормально",
                review_date_text="2026-06-28 09:00:00",
            ),
        ],
    )


def test_twogis_mode_routes_and_tags_provenance(db_session):
    org = _twogis_org(db_session)
    twogis = _FakeScraper(_result())
    public = _FakeScraper(_result())
    service = ScrapeService(db_session, public_scraper=public, twogis_scraper=twogis)

    run = service.create_run(org.id, ScrapeMode.twogis_api)
    service.execute_run(run.id)

    assert twogis.calls == 1
    assert public.calls == 0

    run = service.get_run(run.id)
    assert run.status.value == "success"
    assert run.reviews_inserted == 2

    stored = db_session.query(Review).all()
    assert len(stored) == 2
    assert all(r.scrape_mode == ScrapeMode.twogis_api for r in stored)
    assert all(r.source == "2gis" for r in stored)
    assert all(r.platform == ReviewPlatform.gis2 for r in stored)
    # Analytics (feature 002) still runs for 2GIS reviews.
    assert all(r.sentiment is not None for r in stored)


def test_twogis_second_run_dedups(db_session):
    org = _twogis_org(db_session)
    twogis = _FakeScraper(_result())
    service = ScrapeService(db_session, twogis_scraper=twogis)

    first = service.create_run(org.id, ScrapeMode.twogis_api)
    service.execute_run(first.id)
    second = service.create_run(org.id, ScrapeMode.twogis_api)
    service.execute_run(second.id)

    run = service.get_run(second.id)
    assert run.reviews_inserted == 0
    assert run.reviews_updated == 2
    assert db_session.query(Review).count() == 2
