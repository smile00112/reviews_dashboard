"""HTTP status blocking: a 429/4xx/5xx response is never a real content page,
regardless of what its body says (Yandex rate-limits render as a bare
<pre>limited</pre> body with no captcha wording)."""

from types import SimpleNamespace

from app.scraper.yandex_public import YandexPublicScraper


def test_429_response_is_blocked():
    assert YandexPublicScraper._is_blocked_status(SimpleNamespace(status=429)) is True


def test_200_response_is_not_blocked():
    assert YandexPublicScraper._is_blocked_status(SimpleNamespace(status=200)) is False


def test_none_response_is_not_blocked():
    assert YandexPublicScraper._is_blocked_status(None) is False


def test_challenge_message_reports_status_code():
    message = YandexPublicScraper._challenge_message(SimpleNamespace(status=429))
    assert "429" in message
