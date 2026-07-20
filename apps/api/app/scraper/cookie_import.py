"""Parse cookies an operator copied out of their browser into the storage
state Playwright expects.

Manual import exists because Passport's confirmation-code push is not always
deliverable; pasting a session from an already-authorised browser is the
supported fallback. It is a read-only credential handed over deliberately —
the same one the automated login would have produced.
"""

import json

# The cookie Passport's SSO issues; without it a storage state authorises
# nothing, so importing one is a mistake worth reporting up front rather than
# discovering on the next scrape.
SESSION_COOKIE = "Session_id"
DEFAULT_DOMAIN = ".yandex.ru"
DEFAULT_PATH = "/"

# Chrome/Cookie-Editor spell sameSite differently from Playwright.
_SAME_SITE = {
    "no_restriction": "None",
    "none": "None",
    "lax": "Lax",
    "strict": "Strict",
    "unspecified": "Lax",
}


def _normalise(raw: dict) -> dict | None:
    name = (raw.get("name") or "").strip()
    if not name:
        return None
    expires = raw.get("expires", raw.get("expirationDate"))
    return {
        "name": name,
        "value": raw.get("value") or "",
        "domain": (raw.get("domain") or DEFAULT_DOMAIN).strip(),
        "path": (raw.get("path") or DEFAULT_PATH).strip(),
        # -1 is Playwright's "session cookie, expires with the browser".
        "expires": float(expires) if isinstance(expires, (int, float)) else -1,
        "httpOnly": bool(raw.get("httpOnly", False)),
        "secure": bool(raw.get("secure", True)),
        "sameSite": _SAME_SITE.get(str(raw.get("sameSite", "")).lower(), "Lax"),
    }


def _from_header(text: str) -> list[dict]:
    """Parse a raw `Cookie:` header — name=value pairs separated by `; `."""
    cookies = []
    for chunk in text.split(";"):
        chunk = chunk.strip()
        if not chunk or "=" not in chunk:
            continue
        # Split once only: base64-ish values carry their own '=' padding.
        name, _, value = chunk.partition("=")
        cookies.append({"name": name.strip(), "value": value.strip()})
    return cookies


def parse_cookie_input(text: str) -> list[dict]:
    """Accept a Playwright storage state, a Cookie-Editor JSON export, or a
    raw Cookie header, and return Playwright-shaped cookies.

    Raises ValueError with an actionable message when the input is empty or
    carries no session cookie.
    """
    if not text or not text.strip():
        raise ValueError("Paste cookies exported from a browser where you are signed in to Yandex")

    text = text.strip()
    raw_cookies: list[dict]
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        raw_cookies = _from_header(text)
    else:
        if isinstance(parsed, dict):
            parsed = parsed.get("cookies", [])
        if not isinstance(parsed, list):
            raise ValueError("Unrecognised cookie format — expected a JSON array or a Cookie header")
        raw_cookies = [item for item in parsed if isinstance(item, dict)]

    cookies = [c for c in (_normalise(item) for item in raw_cookies) if c]
    if not any(c["name"] == SESSION_COOKIE and c["value"] for c in cookies):
        raise ValueError(
            f"No {SESSION_COOKIE} cookie found. It is HttpOnly, so document.cookie cannot see it — "
            "export it from DevTools (Application > Cookies) or copy the Cookie request header"
        )
    return cookies


def build_storage_state(cookies: list[dict]) -> dict:
    """Wrap cookies in the storage-state envelope Playwright loads."""
    return {"cookies": cookies, "origins": []}
