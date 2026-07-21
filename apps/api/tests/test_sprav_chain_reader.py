"""SpravChainReader I/O classification, with the network mocked.

The point of these tests is the throttling contract: the cabinet's anti-bot
throttle (an empty preload, or a bounce through Passport) must be classified as
retryable ``throttled`` — not silently swallowed as "no history", and not
mistaken for a hard ``session_expired`` that would abort a whole run.
"""

import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.scraper.yandex_sprav_chain import SpravChainReader

_GOOD_HISTORY = {"initialState": {"edit": {
    "ratingHistory": {"data": {
        "rating_statistic": {"one": 1, "two": 0, "three": 0, "four": 0, "five": 9},
        "rating_history": [{"rating": 4.5, "week": 1753056000000000, "opponents_ratings": []}],
    }},
    "factors": {"strength": 100, "factors": []},
}}}


def _response(*, url="https://yandex.ru/sprav/1/p/edit/rating-history/", status=200, preload=None, text=None):
    if text is None:
        body = json.dumps(preload) if preload is not None else "{}"
        text = f'<script>window.__PRELOAD_DATA = {body};</script>'
    return SimpleNamespace(url=url, status_code=status, text=text)


def _reader(responses):
    """A reader whose session.get yields the given responses in order."""
    reader = SpravChainReader.__new__(SpravChainReader)
    reader.storage_state_path = "unused"
    reader._authenticated = True
    it = iter(responses)
    reader.session = SimpleNamespace(get=lambda *a, **k: next(it))
    return reader


def test_good_page_returns_history():
    reader = _reader([_response(preload=_GOOD_HISTORY)])
    history, error = reader.rating_history("1")
    assert error is None
    assert history.history[0].rating == 4.5


def test_passport_redirect_is_throttled_not_session_expired():
    """A Passport bounce is transient here — the same cookies serve other pages."""
    with patch("app.scraper.yandex_sprav_chain.time.sleep"):
        reader = _reader([_response(url="https://passport.yandex.ru/auth")] * (SpravChainReader.MAX_RETRIES + 1))
        _, error = reader.rating_history("1")
    assert error == "throttled"


def test_empty_preload_is_throttled_not_not_found():
    """The throttle stub is 200 with an empty initialState — not a real 'no history'."""
    with patch("app.scraper.yandex_sprav_chain.time.sleep"):
        reader = _reader([_response(preload={"initialState": {}})] * (SpravChainReader.MAX_RETRIES + 1))
        _, error = reader.rating_history("1")
    assert error == "throttled"


def test_retry_recovers_when_a_later_attempt_succeeds():
    """A throttle that clears mid-backoff must yield the real data, not an error."""
    with patch("app.scraper.yandex_sprav_chain.time.sleep") as sleep:
        reader = _reader([
            _response(preload={"initialState": {}}),          # throttled
            _response(url="https://passport.yandex.ru/auth"), # throttled
            _response(preload=_GOOD_HISTORY),                 # recovered
        ])
        history, error = reader.rating_history("1")
    assert error is None
    assert history.history[0].rating == 4.5
    assert sleep.call_count == 2  # two backoffs before the win


def test_backoff_is_exponential():
    with patch("app.scraper.yandex_sprav_chain.time.sleep") as sleep:
        reader = _reader([_response(preload={"initialState": {}})] * (SpravChainReader.MAX_RETRIES + 1))
        reader.rating_history("1")
    base = SpravChainReader.RETRY_BACKOFF_SECONDS
    assert [c.args[0] for c in sleep.call_args_list] == [base * (2**i) for i in range(SpravChainReader.MAX_RETRIES)]


def test_real_page_without_history_is_not_found_not_throttled():
    """A populated page that simply has no rating history is a real, non-retryable state."""
    populated = {"initialState": {"edit": {"factors": {"strength": 10, "factors": []}}, "user": {"login": "op"}}}
    reader = _reader([_response(preload=populated)])
    history, error = reader.rating_history("1")
    assert error == "rating_history_not_found"
    assert history is None


def test_non_200_is_reported_with_its_status():
    reader = _reader([_response(status=503, text="down")])
    _, error = reader.rating_history("1")
    assert error == "http_503"


def test_missing_session_short_circuits_without_a_request():
    reader = SpravChainReader.__new__(SpravChainReader)
    reader.storage_state_path = "does-not-exist.json"
    reader._authenticated = False
    reader.session = SimpleNamespace(get=lambda *a, **k: pytest.fail("must not hit the network"))
    _, error = reader.rating_history("1")
    assert error == "missing_session"
