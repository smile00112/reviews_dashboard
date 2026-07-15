"""Yandex Sprav (Business cabinet) reader — organization list.

Read-only: the cabinet also exposes editing and review replies; this module
performs GET/read only (constitution hard rule).

The cabinet is a React app that server-renders its state into a
window.__PRELOAD_DATA script tag rather than fetching the list over XHR, so the
list is read out of the page HTML. Parsing is pure and split from the I/O,
mirroring the yandex_http.py / parser.py split.

Note the cabinet lists *chains*, not branches, and carries no rating or review
data at all — those remain the Maps scrapers' job.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field

# The cabinet inlines its state as `window.__PRELOAD_DATA = {...};</script>`.
_PRELOAD_RE = re.compile(r"window\.__PRELOAD_DATA\s*=\s*(\{.*?\})\s*;?\s*</script>", re.S)

# Where the company records live inside that state.
_ORG_ARRAY_PATH: tuple[str, ...] = ("initialState", "companiesList", "listCompanies")


@dataclass
class SpravOrg:
    # permanent_id: the Yandex Maps permalink, the join key to organizations.
    sprav_id: str
    name: str
    address: str | None = None
    url: str | None = None
    org_type: str | None = None
    branch_count: int | None = None
    publishing_status: str | None = None


@dataclass
class SpravListResult:
    organizations: list[SpravOrg] = field(default_factory=list)
    needs_manual_action: bool = False
    error_code: str | None = None
    error_message: str | None = None
    debug_screenshot: str | None = None
    debug_html: str | None = None


def extract_preload_data(html: str) -> dict:
    """Pull the cabinet's inlined state out of the page HTML.

    Returns {} for anything unexpected so a markup change degrades to an empty
    run rather than an exception.
    """
    if not isinstance(html, str):
        return {}
    match = _PRELOAD_RE.search(html)
    if not match:
        return {}
    try:
        data = json.loads(match.group(1))
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def _as_str(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _as_int(value: object) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value) if math.isfinite(value) else None
    return None


def _dig(payload: object, path: tuple[str, ...]) -> object:
    """Walk a nested path, bailing out the moment the shape disagrees."""
    current = payload
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _address(raw: dict) -> str | None:
    """address.formatted is {"value": ..., "locale": ...} — flatten to the value."""
    formatted = (raw.get("address") or {}).get("formatted") if isinstance(raw.get("address"), dict) else None
    if isinstance(formatted, dict):
        return _as_str(formatted.get("value"))
    return _as_str(formatted)


def _main_url(raw: dict) -> str | None:
    """Records carry several urls (main, social); only the main one identifies the org."""
    for entry in raw.get("urls") or []:
        if isinstance(entry, dict) and entry.get("type") == "main":
            return _as_str(entry.get("value"))
    return None


def _parse_one(raw: object) -> SpravOrg | None:
    if not isinstance(raw, dict):
        return None
    sprav_id = _as_str(str(raw["permanent_id"])) if raw.get("permanent_id") is not None else None
    name = _as_str(raw.get("displayName"))
    if not sprav_id or not name:
        return None
    chain = raw.get("chain") if isinstance(raw.get("chain"), dict) else {}
    return SpravOrg(
        sprav_id=sprav_id,
        name=name,
        address=_address(raw),
        url=_main_url(raw),
        org_type=_as_str(raw.get("type")),
        branch_count=_as_int(chain.get("branchCount")),
        publishing_status=_as_str(raw.get("publishing_status")),
    )


def parse_sprav_orgs(preload: object) -> list[SpravOrg]:
    """Map the cabinet's inlined state to SpravOrg records.

    Degrades safely: any unexpected shape yields [] rather than raising.
    """
    raw_list = _dig(preload, _ORG_ARRAY_PATH)
    if not isinstance(raw_list, list):
        return []
    parsed = (_parse_one(item) for item in raw_list)
    return [org for org in parsed if org is not None]
