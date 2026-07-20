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


from app.scraper.yandex_auth import _looks_like_code_screen


def test_looks_like_code_screen_detects_push_code_heading():
    html = "<html><h1>Введите код из пуш-уведомления</h1></html>"
    assert _looks_like_code_screen(html) is True


def test_looks_like_code_screen_detects_generic_confirmation_wording():
    html = "<html><p>Введите код подтверждения, который мы отправили</p></html>"
    assert _looks_like_code_screen(html) is True


def test_looks_like_code_screen_false_for_password_screen():
    html = "<html><h1>Введите пароль</h1></html>"
    assert _looks_like_code_screen(html) is False


def test_login_with_password_without_credentials_short_circuits(tmp_path):
    from app.models.enums import SessionStatus
    from app.scraper.yandex_auth import YandexAuthScraper

    status, message = YandexAuthScraper().login_with_password("", "", str(tmp_path / "state.json"))
    assert status == SessionStatus.missing
    assert "YANDEX_OPERATOR_LOGIN" in message
