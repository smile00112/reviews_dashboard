"""Sprav auth CLI: exit-code contract and the no-credentials short circuit."""

import pytest

from app.models.enums import SessionStatus
from app.scraper.yandex_auth import YandexAuthScraper
from scripts.sprav_login import check_message_for, exit_code_for


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


@pytest.mark.parametrize("status", list(SessionStatus))
def test_check_message_for_covers_every_status(status):
    """Every SessionStatus must produce some non-empty operator-facing text."""
    message = check_message_for(status)
    assert isinstance(message, str) and message


def test_check_message_for_valid_says_session_works():
    assert "works" in check_message_for(SessionStatus.valid)


def test_check_message_for_missing_points_at_login():
    assert "sprav_login" in check_message_for(SessionStatus.missing)


def test_check_message_for_expired_points_at_login_again():
    message = check_message_for(SessionStatus.expired)
    assert "sprav_login" in message
    assert "again" in message


def test_check_message_for_needs_manual_action_mentions_challenge():
    message = check_message_for(SessionStatus.needs_manual_action)
    assert "captcha" in message or "challenge" in message


def test_check_message_for_never_contains_cookie_or_secret_markers():
    for status in SessionStatus:
        message = check_message_for(status).lower()
        assert "session_id" not in message
        assert "cookie" not in message
        assert "storage" not in message
