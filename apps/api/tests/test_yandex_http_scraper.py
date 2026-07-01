from pathlib import Path

from app.scraper.yandex_http import YandexHttpScraper

FIXTURES = Path(__file__).parent / "fixtures"
PAGE_HTML = (FIXTURES / "yandex_http_page.html").read_text(encoding="utf-8")
BOTWALL_HTML = (FIXTURES / "yandex_http_botwall.html").read_text(encoding="utf-8")

URL = "https://yandex.ru/maps/org/test/123/reviews/"


def test_page_url_builds_pagination():
    assert YandexHttpScraper._page_url(URL, 2).endswith("?page=2")
    # Existing page param is replaced, not duplicated.
    assert YandexHttpScraper._page_url(URL + "?page=1", 3).count("page=") == 1


def test_scrape_extracts_reviews(monkeypatch):
    scraper = YandexHttpScraper()

    # Page 1 returns the fixture; subsequent pages are empty (pagination stops).
    def fake_fetch(self, url):
        return PAGE_HTML if url.endswith("page=1") else "<html></html>"

    monkeypatch.setattr(YandexHttpScraper, "_fetch", fake_fetch)

    result = scraper.scrape(URL)
    assert result.error_code is None
    assert result.needs_manual_action is False
    assert len(result.reviews) == 3
    assert result.organization.name == "Кафе Пример"


def test_scrape_dedups_repeated_reviews_across_pages(monkeypatch):
    scraper = YandexHttpScraper()
    # Same HTML on every page → within-run dedup keeps 3, not 3*N.
    monkeypatch.setattr(YandexHttpScraper, "_fetch", lambda self, url: PAGE_HTML)
    result = scraper.scrape(URL)
    assert len(result.reviews) == 3


def test_bot_wall_is_needs_manual_action(monkeypatch):
    scraper = YandexHttpScraper()
    monkeypatch.setattr(YandexHttpScraper, "_fetch", lambda self, url: BOTWALL_HTML)
    result = scraper.scrape(URL)
    assert result.needs_manual_action is True
    assert result.error_code == "access_challenge"
    assert result.debug_html is not None
    assert result.reviews == []


def test_first_page_fetch_failure_is_error(monkeypatch):
    scraper = YandexHttpScraper()
    monkeypatch.setattr(YandexHttpScraper, "_fetch", lambda self, url: None)
    result = scraper.scrape(URL)
    assert result.error_code == "fetch_error"
    assert result.needs_manual_action is False
