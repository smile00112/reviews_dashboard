"""Feature 010 / US4: operator-auth scrape detects challenges at the same
checkpoints as the public scraper and saves debug artifacts."""

from app.scraper import yandex_auth as auth_module
from app.scraper.yandex_auth import YandexAuthScraper
from app.scraper.yandex_public import YandexPublicScraper


class _FakePage:
    def __init__(self, html: str):
        self._html = html

    def content(self) -> str:
        return self._html


def test_challenge_page_yields_needs_manual_action_with_artifacts(monkeypatch):
    saved = {}

    def fake_save(page, prefix):
        saved["prefix"] = prefix
        return "/dbg/shot.png", "/dbg/page.html"

    monkeypatch.setattr(auth_module, "save_debug_artifacts", fake_save)

    public = YandexPublicScraper()
    page = _FakePage("<html>Обнаружена защита от ботов</html>")
    result = YandexAuthScraper._challenge_result(public, page)

    assert result is not None
    assert result.needs_manual_action is True
    assert result.error_code == "access_challenge"
    assert result.debug_screenshot == "/dbg/shot.png"
    assert result.debug_html == "/dbg/page.html"
    assert saved["prefix"] == "auth-challenge"


def test_normal_reviews_page_is_not_a_challenge():
    public = YandexPublicScraper()
    page = _FakePage("<html><div class='business-review-view'>Отличное место</div></html>")
    assert YandexAuthScraper._challenge_result(public, page) is None


def test_missing_storage_state_short_circuits(tmp_path):
    result = YandexAuthScraper().scrape("https://yandex.ru/maps/org/x/1/", str(tmp_path / "absent.json"))
    assert result.needs_manual_action is True
    assert result.error_code == "missing_session"
