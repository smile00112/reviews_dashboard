"""2GIS business-cabinet client (feature 017).

Verifies a manually-imported cabinet session and reads the operator's org list from
the cabinet's own JSON API — the backend the ``account.2gis.com`` SPA talks to:

  * ``GET /api/1.0/users``               — current user (session-validity check)
  * ``GET /api/1.0/orgs?fields=orgDetails`` — the operator's organizations

**Auth is a Bearer access token**, not cookies: the SPA sends
``Authorization: Bearer <access token>`` plus a static ``x-api-key`` (the web client's
``lkApiKeyWeb`` = ``accweb96f8``). The ``spid`` cookie plays no part. The operator pastes the
token (copied from a DevTools request to ``api.account.2gis.com``); it is stored in the
session's storage-state file. This is read-only and drives nothing yet — it exists so the
operator can save a session and confirm it works, by analogy with the Yandex operator session.

Constitution notes: never raises out of an attempt (IV); the token value never appears in
returned messages or logs (VIII). The token is short-lived — an expired one surfaces as
``expired`` (re-import), not a hard failure.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import requests

from app.core.config import settings
from app.models.enums import SessionStatus

ACCOUNT_API = "https://api.account.2gis.com/api/1.0"
CABINET_ORIGIN = "https://account.2gis.com"

# A Bearer token inside an "Authorization: Bearer xxx" line or a raw "Bearer xxx" string.
_BEARER_RE = re.compile(r"[Bb]earer\s+([A-Za-z0-9._\-]+)")
# A bare token pasted on its own (hex session token or a JWT).
_BARE_TOKEN_RE = re.compile(r"^[A-Za-z0-9._\-]{20,}$")


def extract_bearer_token(text: str | None) -> str | None:
    """Pull the access token out of whatever the operator pasted: a full request-headers
    block, an ``Authorization: Bearer …`` line, or the bare token. None when none found."""
    if not text or not text.strip():
        return None
    match = _BEARER_RE.search(text)
    if match:
        return match.group(1)
    for line in text.splitlines():
        candidate = line.strip().strip('"').strip("'").strip(",")
        if _BARE_TOKEN_RE.match(candidate):
            return candidate
    return None


class TwogisAccountScraper:
    REQUEST_TIMEOUT_SECONDS = 30

    def __init__(self, session: requests.Session | None = None) -> None:
        # Injectable for tests; production uses a bare requests session.
        self._http = session or requests.Session()

    # --- public API ---------------------------------------------------------

    def check_session(self, storage_state_path: str) -> tuple[SessionStatus, str]:
        """Verify the saved token against ``GET /users``.

        200 → valid; 400/401/403 → expired (re-import needed); network/other →
        needs_manual_action (transient / geo). Returns (status, terse message)."""
        token = self._load_token(storage_state_path)
        if not token:
            return SessionStatus.missing, "No saved 2GIS cabinet token — import it first"

        try:
            resp = self._http.get(
                f"{ACCOUNT_API}/users",
                headers=self._headers(token),
                timeout=self.REQUEST_TIMEOUT_SECONDS,
            )
        except requests.RequestException as exc:
            return SessionStatus.needs_manual_action, f"Could not reach the 2GIS cabinet API: {type(exc).__name__}"

        if resp.status_code == 200:
            name = self._user_label(resp)
            return SessionStatus.valid, f"2GIS cabinet session works{f' — {name}' if name else ''}"
        if resp.status_code in (400, 401, 403):
            return SessionStatus.expired, "2GIS cabinet token no longer accepted — re-import a fresh one"
        return SessionStatus.needs_manual_action, f"2GIS cabinet API returned HTTP {resp.status_code}"

    def list_orgs(self, storage_state_path: str, limit: int = 1) -> list[dict]:
        """Read the operator's organizations from ``GET /orgs`` — display-only, value fields.

        Returns a trimmed view (id / name / address) for the CLI validator to print. Returns
        an empty list when the token is missing or the call fails; never raises."""
        token = self._load_token(storage_state_path)
        if not token:
            return []
        try:
            resp = self._http.get(
                f"{ACCOUNT_API}/orgs",
                params={"fields": "orgDetails"},
                headers=self._headers(token),
                timeout=self.REQUEST_TIMEOUT_SECONDS,
            )
            resp.raise_for_status()
            data = resp.json()
        except (requests.RequestException, ValueError):
            return []

        items = self._extract_org_items(data)
        return [self._trim_org(item) for item in items[:limit]]

    # --- helpers ------------------------------------------------------------

    @staticmethod
    def _headers(token: str) -> dict:
        return {
            "User-Agent": settings.http_scrape_user_agent,
            "Accept": "application/json, text/plain, */*",
            "Authorization": f"Bearer {token}",
            "x-api-key": settings.twogis_lk_api_key,
            "locale": "ru",
            "Origin": CABINET_ORIGIN,
            "Referer": f"{CABINET_ORIGIN}/",
        }

    @staticmethod
    def _load_token(storage_state_path: str) -> str | None:
        """Read the access token out of the session's storage-state file (shape
        ``{"access_token": "…"}``). None → no usable file. Never raises."""
        path = Path(storage_state_path)
        if not path.exists() or path.stat().st_size == 0:
            return None
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        token = state.get("access_token") if isinstance(state, dict) else None
        return token or None

    @staticmethod
    def _user_label(resp: requests.Response) -> str | None:
        """A non-sensitive label (email) from GET /users to confirm *whose* cabinet — never
        the token. Best-effort; returns None on any parse issue."""
        try:
            result = (resp.json() or {}).get("result") or {}
            return result.get("email") or result.get("name")
        except ValueError:
            return None

    @staticmethod
    def _extract_org_items(data: object) -> list[dict]:
        """Pull the org array out of the cabinet response. GET /orgs returns
        ``{"result": {"items": [...]}}``; tolerate a couple of nearby shapes."""
        if isinstance(data, list):
            return [x for x in data if isinstance(x, dict)]
        if isinstance(data, dict):
            result = data.get("result")
            if isinstance(result, dict):
                items = result.get("items")
                if isinstance(items, list):
                    return [x for x in items if isinstance(x, dict)]
            if isinstance(result, list):
                return [x for x in result if isinstance(x, dict)]
        return []

    @staticmethod
    def _trim_org(item: dict) -> dict:
        return {
            "id": item.get("id") or item.get("org_id"),
            "name": item.get("name") or item.get("title"),
            "address": item.get("address") or item.get("address_name"),
            "branchesCount": item.get("branchesCount"),
        }
