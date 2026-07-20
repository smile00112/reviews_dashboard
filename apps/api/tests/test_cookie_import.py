"""Manual cookie import: turn whatever an operator can copy out of their
browser into a Playwright storage-state file.

Three shapes are accepted because the practical export routes differ:
a Playwright storage state, a Cookie-Editor style JSON array, and the raw
`Cookie:` request header. Session_id is HttpOnly, so `document.cookie` can
never produce it — the parser must reject input that lacks it rather than
write a storage state that silently fails on the next scrape.
"""

import json

import pytest

from app.scraper.cookie_import import build_storage_state, parse_cookie_input

SESSION_VALUE = "3:1234567890.5.0.1234567890:abcdef:1.1|123456789.0.2|:xyz"


def test_parses_a_playwright_storage_state():
    raw = json.dumps(
        {
            "cookies": [
                {"name": "Session_id", "value": SESSION_VALUE, "domain": ".yandex.ru", "path": "/"},
            ],
            "origins": [],
        }
    )

    cookies = parse_cookie_input(raw)

    assert [c["name"] for c in cookies] == ["Session_id"]
    assert cookies[0]["value"] == SESSION_VALUE


def test_parses_a_cookie_editor_export():
    raw = json.dumps(
        [
            {
                "domain": ".yandex.ru",
                "name": "Session_id",
                "value": SESSION_VALUE,
                "path": "/",
                "httpOnly": True,
                "secure": True,
                "sameSite": "no_restriction",
                "expirationDate": 1800000000.5,
            },
            {"domain": ".yandex.ru", "name": "yandexuid", "value": "42", "path": "/"},
        ]
    )

    cookies = parse_cookie_input(raw)

    assert {c["name"] for c in cookies} == {"Session_id", "yandexuid"}
    session = next(c for c in cookies if c["name"] == "Session_id")
    assert session["sameSite"] == "None", "Chrome's no_restriction must map to Playwright's None"
    assert session["expires"] == 1800000000.5


def test_parses_a_raw_cookie_header():
    raw = f"Session_id={SESSION_VALUE}; yandexuid=42; i=abc"

    cookies = parse_cookie_input(raw)

    assert {c["name"] for c in cookies} == {"Session_id", "yandexuid", "i"}
    assert all(c["domain"] == ".yandex.ru" for c in cookies)


def test_raw_header_keeps_values_containing_equals_signs():
    raw = f"Session_id={SESSION_VALUE}; L=padded=="

    cookies = parse_cookie_input(raw)

    assert next(c for c in cookies if c["name"] == "L")["value"] == "padded=="


def test_rejects_input_without_the_session_cookie():
    with pytest.raises(ValueError, match="Session_id"):
        parse_cookie_input("yandexuid=42; i=abc")


def test_rejects_blank_input():
    with pytest.raises(ValueError):
        parse_cookie_input("   ")


def test_build_storage_state_shape_matches_playwright():
    state = build_storage_state(parse_cookie_input(f"Session_id={SESSION_VALUE}"))

    assert state["origins"] == []
    cookie = state["cookies"][0]
    assert set(cookie) == {"name", "value", "domain", "path", "expires", "httpOnly", "secure", "sameSite"}
    assert cookie["sameSite"] in {"Strict", "Lax", "None"}
