"""Sprav scraper I/O contract: session preconditions and challenge detection.

Playwright itself is not exercised (constitution: no live-network tests); only
the pure seams are.
"""

from app.scraper.yandex_sprav import YandexSpravScraper


def test_missing_storage_state_short_circuits(tmp_path):
    """No session file must not launch a browser."""
    result = YandexSpravScraper().list_organizations(str(tmp_path / "absent.json"))
    assert result.needs_manual_action is True
    assert result.error_code == "missing_session"
    assert result.organizations == []


def test_empty_storage_state_short_circuits(tmp_path):
    state = tmp_path / "empty.json"
    state.write_text("", encoding="utf-8")
    result = YandexSpravScraper().list_organizations(str(state))
    assert result.needs_manual_action is True
    assert result.error_code == "missing_session"


def test_passport_redirect_is_a_challenge():
    """An expired session bounces to Passport — that needs a human, not a retry."""
    assert YandexSpravScraper._is_challenge("<html>ok</html>", "https://passport.yandex.ru/auth") is True


def test_bot_marker_is_a_challenge():
    assert YandexSpravScraper._is_challenge(
        "<html>Обнаружена защита от ботов</html>", "https://yandex.ru/sprav/companies"
    ) is True


def test_rendered_cabinet_page_is_not_a_challenge():
    assert YandexSpravScraper._is_challenge(
        "<html><script>window.__PRELOAD_DATA = {};</script></html>",
        "https://yandex.ru/sprav/companies",
    ) is False
