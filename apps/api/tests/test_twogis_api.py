"""Tests for the 2GIS reviews API scraper (twogis_api mode, feature 006)."""

import requests

from app.models.enums import ReviewPlatform, ScrapeMode
from app.models.organization import Organization
from app.models.review import Review
from app.scraper.twogis_api import CATALOG_URL, TwogisApiScraper
from app.scraper.types import ParsedOrganization, ParsedReview, ScrapeResult
from app.services.scrape_service import ScrapeService

FULL_URL = "https://2gis.ru/achinsk/firm/70000001027742089/tab/reviews"
FIRM_ID = "70000001027742089"

CATALOG = {
    "meta": {"code": 200},
    "result": {
        "items": [
            {
                "name": "Суши мастер, служба доставки",
                "org": {"id": "70000001027742088"},
                # general_* = this branch; org_* = parent franchise aggregate.
                # A multi-branch franchise must report the BRANCH figures.
                "reviews": {
                    "org_rating": 4.2,
                    "org_review_count": 654,
                    "org_review_count_with_stars": 700,
                    "general_rating": 4.7,
                    "general_review_count": 294,
                    "general_review_count_with_stars": 320,
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
            "object": {"id": FIRM_ID},
            "official_answer": {"text": "Спасибо за отзыв!"},
        },
        {
            "id": "r2",
            "user": {"name": "Жанна Гаврилова"},
            "rating": 4,
            "text": "Нормально",
            "date_created": "2026-06-28 09:00:00",
            "object": {"id": FIRM_ID},
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


def test_map_review_excludes_invalid_ratings():
    """FR-010 (feature 010): sub-1 / missing ratings never reach persistence,
    matching the Yandex parser guard."""
    for bad_rating in (None, "abc", 0, -1):
        assert (
            TwogisApiScraper._map_review(
                {"user": {}, "rating": bad_rating, "text": "x", "date_created": "", "official_answer": None}
            )
            is None
        )


def test_map_review_degrades_safely_on_missing_optional_fields():
    pr = TwogisApiScraper._map_review(
        {"user": {}, "rating": 4, "text": None, "date_created": "", "official_answer": None}
    )
    assert pr is not None
    assert pr.rating == 4
    assert pr.review_text == ""
    assert pr.review_date_text is None
    assert pr.review_date is None
    assert pr.response_text is None


def test_map_review_converts_source_offset_to_moscow_date():
    """2GIS stamps date_created in the BRANCH's own UTC offset. Slicing the first
    10 characters kept that local day, so a review posted just after midnight in
    Novosibirsk (+07:00) was stored as a date still in the future for an operator
    on Moscow time. The instant must be converted to MSK before taking the day."""
    pr = TwogisApiScraper._map_review(
        {
            "id": "r9",
            "user": {"name": "Ларочка"},
            "rating": 5,
            "text": "Прекрасные роллы",
            "date_created": "2026-07-20T00:03:31.0+07:00",
        }
    )
    assert pr.review_date is not None
    assert pr.review_date.isoformat() == "2026-07-19"
    # The raw timestamp still feeds the content_hash verbatim.
    assert pr.review_date_text == "2026-07-20T00:03:31.0+07:00"


def test_map_review_keeps_moscow_day_for_utc_timestamps():
    # 21:30 UTC is already the next day in MSK (+03:00).
    pr = TwogisApiScraper._map_review(
        {"id": "r10", "user": {}, "rating": 4, "text": "x", "date_created": "2026-07-19T21:30:00Z"}
    )
    assert pr.review_date.isoformat() == "2026-07-20"


def test_fetch_reviews_skips_invalid_rating_entries(monkeypatch):
    scraper = TwogisApiScraper()
    payload = {
        "reviews": [
            {"id": "ok", "user": {"name": "A"}, "rating": 5, "text": "good", "date_created": "2026-07-01 10:00:00"},
            {"id": "bad", "user": {"name": "B"}, "rating": 0, "text": "no rating", "date_created": "2026-07-01 11:00:00"},
        ],
        "meta": {},
    }
    monkeypatch.setattr(scraper, "_get_json", lambda url, params: (payload, None))
    collected, _exhausted = scraper._fetch_reviews("123", "456")
    assert [r.external_review_id for r in collected] == ["ok"]


# --- branch scoping --------------------------------------------------------


def _branch_payload(*object_ids, next_link=None):
    return {
        "meta": {"next_link": next_link} if next_link else {},
        "reviews": [
            {
                "id": f"r{i}",
                "user": {"name": f"U{i}"},
                "rating": 5,
                "text": "ok",
                "date_created": "2026-07-01T10:00:00+03:00",
                **({"object": {"id": oid}} if oid is not None else {}),
            }
            for i, oid in enumerate(object_ids)
        ],
    }


def test_fetch_reviews_keeps_only_the_requested_branch(monkeypatch):
    """``/orgs/{org_id}/reviews`` serves the whole FRANCHISE pool — every branch of
    a multi-branch org shares one org_id. Persisting the pool under a single branch
    inflated its review count far past the branch counter 2GIS shows on the card
    (observed: 42 on the card vs 150 stored). Each review names its own branch in
    ``object.id``; only those belong to this organization."""
    scraper = TwogisApiScraper()
    payload = _branch_payload(FIRM_ID, "70000009999999999", FIRM_ID, "70000008888888888")
    monkeypatch.setattr(scraper, "_get_json", lambda url, params: (payload, None))
    collected, exhausted = scraper._fetch_reviews("70000001027742088", FIRM_ID)
    assert [r.external_review_id for r in collected] == ["r0", "r2"]
    assert exhausted is True


def test_fetch_reviews_keeps_reviews_without_an_object_id(monkeypatch):
    # Single-branch orgs may omit `object`; absence must not silently drop reviews.
    scraper = TwogisApiScraper()
    monkeypatch.setattr(
        scraper, "_get_json", lambda url, params: (_branch_payload(None, FIRM_ID), None)
    )
    collected, _ = scraper._fetch_reviews("70000001027742088", FIRM_ID)
    assert [r.external_review_id for r in collected] == ["r0", "r1"]


def test_fetch_reviews_limit_counts_only_kept_reviews(monkeypatch):
    """The cap bounds reviews we KEEP, not pool rows walked — otherwise a franchise
    branch's own reviews get cut short by its siblings' volume."""
    scraper = TwogisApiScraper()
    payload = _branch_payload("70000009999999999", FIRM_ID, "70000009999999999", FIRM_ID)
    monkeypatch.setattr(scraper, "_get_json", lambda url, params: (payload, None))
    collected, exhausted = scraper._fetch_reviews("70000001027742088", FIRM_ID, limit=2)
    assert [r.external_review_id for r in collected] == ["r1", "r3"]
    # The cap cut the walk short, so coverage is unproven.
    assert exhausted is False


def test_fetch_reviews_does_not_filter_by_rated(monkeypatch):
    """``rated=true`` silently dropped ordinary rated reviews (5 of 42 on the
    observed org), leaving the collected count permanently below the platform
    counter so a full pass could never corroborate."""
    seen = {}
    scraper = TwogisApiScraper()

    def fake(url, params):
        seen.update(params)
        return _branch_payload(FIRM_ID), None

    monkeypatch.setattr(scraper, "_get_json", fake)
    scraper._fetch_reviews("70000001027742088", FIRM_ID)
    assert "rated" not in seen


def test_scrape_filters_pool_to_the_requested_branch(monkeypatch):
    pool = _branch_payload(FIRM_ID, "70000009999999999")
    monkeypatch.setattr(TwogisApiScraper, "_get_json", _fake_get_json(reviews=pool))
    result = TwogisApiScraper().scrape(FULL_URL)
    assert [r.external_review_id for r in result.reviews] == ["r0"]


# --- firm id resolution ----------------------------------------------------


def test_resolve_firm_id_from_full_url_no_network(monkeypatch):
    def boom(self, url):
        raise AssertionError("proxy must not be called for a full /firm/ URL")

    monkeypatch.setattr(TwogisApiScraper, "_proxy_html", boom)
    firm_id, challenge = TwogisApiScraper()._resolve_firm_id(FULL_URL)
    assert firm_id == "70000001027742089"
    assert challenge is None


def test_resolve_firm_id_short_link_via_redirect_no_proxy(monkeypatch):
    # go.2gis.com redirects to a URL already containing the firm id, even though
    # the final SPA page 403s from a datacenter IP — no proxy is needed to read it.
    class FakeResponse:
        url = (
            "https://2gis.ru/ishim/search/name/firm/70000001034286619/69.48,56.11"
        )

    def fake_get(url, headers=None, timeout=None, allow_redirects=None):
        assert allow_redirects is True
        return FakeResponse()

    monkeypatch.setattr("app.scraper.twogis_api.requests.get", fake_get)

    def boom(self, url):
        raise AssertionError("_proxy_html should not be called when redirect resolves")

    monkeypatch.setattr(TwogisApiScraper, "_proxy_html", boom)
    firm_id, challenge = TwogisApiScraper()._resolve_firm_id("https://go.2gis.com/xbrHO")
    assert firm_id == "70000001034286619"
    assert challenge is None


def test_resolve_via_redirect_reads_museum_interstitial_return_url(monkeypatch):
    # 2GIS sometimes routes the short link through a /museum interstitial instead
    # of the firm page — the real destination is in its return_url query param.
    class FakeResponse:
        url = (
            "https://2gis.ru/museum?return_url=https%3A%2F%2F2gis.ru%2Fspb%2Fbranches"
            "%2F70000001036318139%2Ffirm%2F70000001041151499%2F30.22%2C6.5"
        )

    monkeypatch.setattr(
        "app.scraper.twogis_api.requests.get", lambda *a, **k: FakeResponse()
    )
    scraper = TwogisApiScraper()
    firm_id = scraper._resolve_via_redirect("https://go.2gis.com/wgSo1")
    assert firm_id == "70000001041151499"


def test_resolve_via_redirect_retries_transient_connection_error(monkeypatch):
    calls = {"n": 0}

    class FakeResponse:
        url = "https://2gis.ru/x/firm/70000001028349013/1,2"

    def flaky_get(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise requests.exceptions.ConnectionError("reset")
        return FakeResponse()

    monkeypatch.setattr("app.scraper.twogis_api.requests.get", flaky_get)
    scraper = TwogisApiScraper()
    firm_id = scraper._resolve_via_redirect("https://go.2gis.com/q1Evm")
    assert firm_id == "70000001028349013"
    assert calls["n"] == 2


def test_resolve_firm_id_short_link_picks_dominant_id(monkeypatch):
    html = '<a href="/firm/999">a</a><a href="/firm/999">b</a><a href="/firm/111">c</a>'
    # Redirect resolution is tried first; force the fallback-to-page-body path.
    monkeypatch.setattr(TwogisApiScraper, "_resolve_via_redirect", lambda self, url: None)
    monkeypatch.setattr(TwogisApiScraper, "_proxy_html", lambda self, url: (html, None))
    firm_id, challenge = TwogisApiScraper()._resolve_firm_id("https://go.2gis.com/xbrHO")
    assert firm_id == "999"
    assert challenge is None


def test_short_link_without_proxy_key_needs_manual_action(monkeypatch):
    # No proxy pool AND no ScrapeOps key → short link cannot be resolved offline.
    monkeypatch.setattr("app.scraper.twogis_api.settings.proxy_pool", "")
    monkeypatch.setattr("app.scraper.twogis_api.settings.scrapeops_api_key", "")
    monkeypatch.setattr(TwogisApiScraper, "_resolve_via_redirect", lambda self, url: None)
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
    # Branch-level (general_*), not the franchise aggregate (org_*).
    assert result.organization.rating == 4.7
    assert result.organization.review_count == 294
    assert result.organization.rating_count == 320
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
    # The 2GIS link belongs in gis2_url, not yandex_url: twogis_api scrapes its own
    # platform's column. (This fixture used to stash it in yandex_url, which only
    # worked while ScrapeService fed every mode the Yandex URL — see
    # tests/test_scrape_url_routing.py.)
    org = Organization(
        gis2_url="https://2gis.ru/achinsk/firm/70000001027742089",
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
