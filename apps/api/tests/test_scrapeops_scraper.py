from pathlib import Path

import pytest

from app.scraper.yandex_scrapeops import YandexScrapeOpsScraper

FIXTURES = Path(__file__).parent / "fixtures"
PAGE_HTML = (FIXTURES / "yandex_http_page.html").read_text(encoding="utf-8")
BOTWALL_HTML = (FIXTURES / "yandex_http_botwall.html").read_text(encoding="utf-8")

URL = "https://yandex.ru/maps/org/test/123/reviews/"


def test_missing_api_key_is_needs_manual_action(monkeypatch):
    monkeypatch.setattr("app.scraper.yandex_scrapeops.settings.scrapeops_api_key", "")
    result = YandexScrapeOpsScraper().scrape(URL)
    assert result.needs_manual_action is True
    assert result.error_code == "no_api_key"
    assert result.reviews == []


def test_invalid_api_key_is_needs_manual_action(monkeypatch):
    monkeypatch.setattr("app.scraper.yandex_scrapeops.settings.scrapeops_api_key", "bad-key")
    scraper = YandexScrapeOpsScraper()
    monkeypatch.setattr(
        YandexScrapeOpsScraper,
        "_fetch",
        lambda self, url: (None, __import__("app.scraper.types", fromlist=["ScrapeResult"]).ScrapeResult(
            needs_manual_action=True,
            error_code="invalid_api_key",
            error_message="ScrapeOps rejected API key: HTTP 401",
        )),
    )
    result = scraper.scrape(URL)
    assert result.needs_manual_action is True
    assert result.error_code == "invalid_api_key"


def test_bot_wall_is_needs_manual_action(monkeypatch):
    monkeypatch.setattr("app.scraper.yandex_scrapeops.settings.scrapeops_api_key", "test-key")
    monkeypatch.setattr(
        YandexScrapeOpsScraper,
        "_fetch",
        lambda self, url: (BOTWALL_HTML, None),
    )
    result = YandexScrapeOpsScraper().scrape(URL)
    assert result.needs_manual_action is True
    assert result.error_code == "access_challenge"
    assert result.debug_html is not None
    assert result.reviews == []


def test_scrape_extracts_reviews(monkeypatch):
    monkeypatch.setattr("app.scraper.yandex_scrapeops.settings.scrapeops_api_key", "test-key")
    monkeypatch.setattr("app.scraper.yandex_scrapeops.settings.scrapeops_max_pages", 3)

    def fake_fetch(self, url):
        return (PAGE_HTML, None) if "page=1" in url else ("<html></html>", None)

    monkeypatch.setattr(YandexScrapeOpsScraper, "_fetch", fake_fetch)
    result = YandexScrapeOpsScraper().scrape(URL)
    assert result.error_code is None
    assert result.needs_manual_action is False
    assert len(result.reviews) == 3
    assert result.organization.name == "Кафе Пример"


def test_empty_first_page_returns_no_reviews(monkeypatch):
    monkeypatch.setattr("app.scraper.yandex_scrapeops.settings.scrapeops_api_key", "test-key")
    monkeypatch.setattr(
        YandexScrapeOpsScraper,
        "_fetch",
        lambda self, url: ("<html></html>", None),
    )
    result = YandexScrapeOpsScraper().scrape(URL)
    assert result.error_code is None
    assert result.reviews == []


def test_page_url_builds_pagination():
    assert YandexScrapeOpsScraper._page_url(URL, 2).endswith("?page=2")
    assert YandexScrapeOpsScraper._page_url(URL + "?page=1", 3).count("page=") == 1
