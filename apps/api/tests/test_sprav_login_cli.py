"""Sprav auth CLI: exit-code contract and the no-credentials short circuit."""

import pytest

from app.models.enums import SessionStatus
from app.scraper.yandex_auth import YandexAuthScraper
from scripts.sprav_login import exit_code_for


@pytest.mark.parametrize("status,expected", [
    (SessionStatus.valid, 0),
    (SessionStatus.needs_manual_action, 2),
    (SessionStatus.missing, 1),
    (SessionStatus.expired, 1),
])
def test_exit_code_for(status, expected):
    assert exit_code_for(status) == expected


def test_login_without_credentials_short_circuits(tmp_path):
    """No creds must not launch a browser — it returns `missing` immediately."""
    status, message = YandexAuthScraper().login("", "", str(tmp_path / "state.json"))
    assert status == SessionStatus.missing
    assert "YANDEX_OPERATOR_LOGIN" in message


def test_session_cookie_present_is_detected():
    cookies = [
        {"name": "yandexuid", "value": "123", "domain": ".yandex.ru"},
        {"name": "Session_id", "value": "3:abc", "domain": ".yandex.ru"},
    ]
    assert YandexAuthScraper._has_session_cookie(cookies) is True


def test_no_cookies_is_not_logged_in():
    assert YandexAuthScraper._has_session_cookie([]) is False


def test_other_cookies_alone_are_not_a_session():
    cookies = [{"name": "yandexuid", "value": "123", "domain": ".yandex.ru"}]
    assert YandexAuthScraper._has_session_cookie(cookies) is False


def test_empty_session_value_is_not_a_session():
    cookies = [{"name": "Session_id", "value": "", "domain": ".yandex.ru"}]
    assert YandexAuthScraper._has_session_cookie(cookies) is False


def test_session_cookie_on_a_foreign_domain_is_ignored():
    cookies = [{"name": "Session_id", "value": "3:abc", "domain": ".example.com"}]
    assert YandexAuthScraper._has_session_cookie(cookies) is False
