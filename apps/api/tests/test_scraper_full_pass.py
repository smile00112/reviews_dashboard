"""full_pass coverage semantics (feature 011).

full_pass=True must be provable: pagination exhausted before any limit/max_pages
cap, with no page skipped. Anything else — including "can't tell" — is False,
because downstream removal marking trusts this flag.
"""

from pathlib import Path

from app.scraper.twogis_api import TwogisApiScraper
from app.scraper.yandex_http import YandexHttpScraper

FIXTURES = Path(__file__).parent / "fixtures"
PAGE_HTML = (FIXTURES / "yandex_http_page.html").read_text(encoding="utf-8")  # 3 reviews
BOTWALL_HTML = (FIXTURES / "yandex_http_botwall.html").read_text(encoding="utf-8")
EMPTY_HTML = "<html></html>"

URL = "https://yandex.ru/maps/org/test/123/reviews/"


# --- yandex_http ---------------------------------------------------------


def test_http_full_pass_on_exhausted_pagination(monkeypatch):
    scraper = YandexHttpScraper()
    monkeypatch.setattr(
        YandexHttpScraper, "_fetch", lambda self, url: PAGE_HTML if url.endswith("page=1") else EMPTY_HTML
    )
    result = scraper.scrape(URL)
    assert result.error_code is None
    assert len(result.reviews) == 3
    assert result.full_pass is True


def test_http_full_pass_when_last_page_repeats(monkeypatch):
    # Yandex serves the last page again past the end: all-dup page => exhausted.
    scraper = YandexHttpScraper()
    monkeypatch.setattr(YandexHttpScraper, "_fetch", lambda self, url: PAGE_HTML)
    result = scraper.scrape(URL, max_pages=3)
    assert len(result.reviews) == 3
    assert result.full_pass is True


def test_http_not_full_when_limit_cap_hit(monkeypatch):
    scraper = YandexHttpScraper()
    monkeypatch.setattr(
        YandexHttpScraper, "_fetch", lambda self, url: PAGE_HTML if url.endswith("page=1") else EMPTY_HTML
    )
    result = scraper.scrape(URL, limit=2)
    assert len(result.reviews) == 2
    assert result.full_pass is False


def test_http_not_full_when_max_pages_cap_hit(monkeypatch):
    # Every page yields fresh content and max_pages stops the walk mid-list.
    def fake_fetch(self, url):
        page = int(url.rsplit("page=", 1)[1])
        # Unique review texts per page => always fresh, pagination never exhausts.
        return PAGE_HTML.replace("Отличное", f"Отличное-{page}")

    scraper = YandexHttpScraper()
    monkeypatch.setattr(YandexHttpScraper, "_fetch", fake_fetch)
    result = scraper.scrape(URL, max_pages=2)
    assert result.full_pass is False


def test_http_not_full_when_a_page_was_skipped(monkeypatch):
    # Page 2 fails transiently (skipped hole), page 3 exhausts. Coverage has a
    # hole => never full, even though the loop ended via exhaustion.
    def fake_fetch(self, url):
        page = int(url.rsplit("page=", 1)[1])
        if page == 1:
            return PAGE_HTML
        if page == 2:
            return None
        return EMPTY_HTML

    scraper = YandexHttpScraper()
    monkeypatch.setattr(YandexHttpScraper, "_fetch", fake_fetch)
    result = scraper.scrape(URL)
    assert result.error_code is None
    assert result.full_pass is False


def test_http_not_full_on_bot_wall(monkeypatch):
    scraper = YandexHttpScraper()
    monkeypatch.setattr(YandexHttpScraper, "_fetch", lambda self, url: BOTWALL_HTML)
    result = scraper.scrape(URL)
    assert result.needs_manual_action is True
    assert result.full_pass is False


def test_http_not_full_on_first_page_error(monkeypatch):
    scraper = YandexHttpScraper()
    monkeypatch.setattr(YandexHttpScraper, "_fetch", lambda self, url: None)
    result = scraper.scrape(URL)
    assert result.error_code == "fetch_error"
    assert result.full_pass is False


def test_http_metrics_only_never_full(monkeypatch):
    scraper = YandexHttpScraper()
    monkeypatch.setattr(YandexHttpScraper, "_fetch", lambda self, url: PAGE_HTML)
    result = scraper.scrape(URL, metrics_only=True)
    assert result.full_pass is False


# --- twogis_api ----------------------------------------------------------


def _review(i: int) -> dict:
    return {
        "id": f"r{i}",
        "user": {"name": f"User {i}"},
        "rating": 5,
        "text": f"Отзыв номер {i}",
        "date_created": f"2026-07-{i:02d} 10:00:00",
    }


def test_twogis_full_pass_on_natural_end(monkeypatch):
    scraper = TwogisApiScraper()
    page = {"meta": {}, "reviews": [_review(1), _review(2)]}  # no next_link => end
    monkeypatch.setattr(scraper, "_get_json", lambda url, params: (page, None))
    reviews, exhausted = scraper._fetch_reviews("123")
    assert len(reviews) == 2
    assert exhausted is True


def test_twogis_full_pass_on_empty_page(monkeypatch):
    pages = [
        {"meta": {"next_link": "next"}, "reviews": [_review(1)]},
        {"meta": {}, "reviews": []},
    ]
    scraper = TwogisApiScraper()
    monkeypatch.setattr(scraper, "_get_json", lambda url, params: (pages.pop(0), None))
    reviews, exhausted = scraper._fetch_reviews("123")
    assert len(reviews) == 1
    assert exhausted is True


def test_twogis_not_full_when_limit_cap_hit(monkeypatch):
    scraper = TwogisApiScraper()
    page = {"meta": {"next_link": "next"}, "reviews": [_review(1), _review(2), _review(3)]}
    monkeypatch.setattr(scraper, "_get_json", lambda url, params: (page, None))
    reviews, exhausted = scraper._fetch_reviews("123", limit=2)
    assert len(reviews) == 2
    assert exhausted is False


def test_twogis_not_full_when_max_pages_cap_hit(monkeypatch):
    scraper = TwogisApiScraper()
    page = {"meta": {"next_link": "next"}, "reviews": [_review(1)]}
    monkeypatch.setattr(scraper, "_get_json", lambda url, params: (page, None))
    reviews, exhausted = scraper._fetch_reviews("123", max_pages=1)
    assert exhausted is False


def test_twogis_not_full_on_mid_pagination_error(monkeypatch):
    pages = [
        ({"meta": {"next_link": "next"}, "reviews": [_review(1)]}, None),
        (None, "boom"),
    ]
    scraper = TwogisApiScraper()
    monkeypatch.setattr(scraper, "_get_json", lambda url, params: pages.pop(0))
    reviews, exhausted = scraper._fetch_reviews("123")
    assert len(reviews) == 1
    assert exhausted is False


def test_twogis_scrape_sets_result_full_pass(monkeypatch):
    from tests.test_twogis_api import CATALOG, FULL_URL
    from app.scraper.twogis_api import CATALOG_URL

    page = {"meta": {}, "reviews": [_review(1)]}

    def fake_get_json(self, url, params):
        if url == CATALOG_URL:
            return CATALOG, None
        return page, None

    monkeypatch.setattr(TwogisApiScraper, "_get_json", fake_get_json)
    result = TwogisApiScraper().scrape(FULL_URL)
    assert result.error_code is None
    assert result.full_pass is True
    # metrics_only claims no review coverage.
    result_metrics = TwogisApiScraper().scrape(FULL_URL, metrics_only=True)
    assert result_metrics.full_pass is False
