"""Feature 010 / US4: operator-auth scrape detects challenges at the same
checkpoints as the public scraper and saves debug artifacts."""

from types import SimpleNamespace

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


def test_429_response_yields_needs_manual_action(monkeypatch):
    saved = {}

    def fake_save(page, prefix):
        saved["prefix"] = prefix
        return "/dbg/shot.png", "/dbg/page.html"

    monkeypatch.setattr(auth_module, "save_debug_artifacts", fake_save)

    public = YandexPublicScraper()
    page = _FakePage("<html><pre>limited</pre></html>")
    response = SimpleNamespace(status=429)
    result = YandexAuthScraper._challenge_result(public, page, response)

    assert result is not None
    assert result.needs_manual_action is True
    assert result.error_code == "access_challenge"
    assert "429" in result.error_message
    assert saved["prefix"] == "auth-challenge"


def test_missing_storage_state_short_circuits(tmp_path):
    result = YandexAuthScraper().scrape("https://yandex.ru/maps/org/x/1/", str(tmp_path / "absent.json"))
    assert result.needs_manual_action is True
    assert result.error_code == "missing_session"


from app.scraper.yandex_auth import _is_code_screen

# URLs captured from a live Passport run on 2026-07-20. The previous
# HTML-marker detector was replaced because "код из"/"введите код"/"пароль"
# all appear in the bundled JS of *every* Passport screen — the markers hit
# 6-26 times on the plain login screen, so they never discriminated anything.


def test_is_code_screen_detects_the_push_code_step():
    url = "https://passport.yandex.ru/pwl-yandex/auth/push-code?cause=auth&process_uuid=db054be9"
    assert _is_code_screen(url) is True


def test_is_code_screen_false_for_the_login_step():
    url = "https://passport.yandex.ru/pwl-yandex/auth/add?cause=auth&process_uuid=db054be9"
    assert _is_code_screen(url) is False


def test_is_code_screen_false_for_missing_url():
    assert _is_code_screen("") is False
    assert _is_code_screen(None) is False


def test_login_with_password_without_credentials_short_circuits(tmp_path):
    from app.models.enums import SessionStatus
    from app.scraper.yandex_auth import YandexAuthScraper

    status, message = YandexAuthScraper().login_with_password("", "", str(tmp_path / "state.json"))
    assert status == SessionStatus.missing
    assert "YANDEX_OPERATOR_LOGIN" in message
