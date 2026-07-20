"""Yandex Sprav (Business cabinet) reader — chain branches and rating history.

Read-only, like its sibling ``yandex_sprav`` (constitution hard rule): the
cabinet also exposes editing, and none of it is touched here.

Both cabinet pages server-render their whole state into ``window.__PRELOAD_DATA``
rather than fetching over XHR, so they are readable **browserless** — plain
``requests`` plus the operator's saved Passport cookies, no Playwright. Parsing
is pure and split from the I/O, mirroring the yandex_http.py / parser.py split.

Two pages are read:

* ``/sprav/chain/<chain_id>/branches?page=N`` — the chain's branch list. Carries
  each branch's permalink (the join key to ``organizations.external_id``),
  address, and its *current* rating/review count.
* ``/sprav/<permalink>/p/edit/rating-history/`` — one branch's **weekly** rating
  history, star distribution, and card-completeness factors.

The weekly history has no per-week review count — the cabinet simply does not
publish one. Callers must keep that as ``None`` rather than inventing a zero.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path

import requests

from app.core.config import settings
from app.scraper.markers import BOT_MARKERS
from app.scraper.yandex_sprav import extract_preload_data

_BRANCH_LIST_PATH: tuple[str, ...] = ("initialState", "chain", "companyList", "companies")
_PAGER_PATH: tuple[str, ...] = ("initialState", "chain", "companyList", "pager")
_CHAIN_NAME_PATH: tuple[str, ...] = ("initialState", "chain", "chain", "displayName")
_RATING_HISTORY_PATH: tuple[str, ...] = ("initialState", "edit", "ratingHistory", "data")
_FACTORS_PATH: tuple[str, ...] = ("initialState", "edit", "factors")

# The cabinet renders five fixed star buckets in this order.
_STAR_KEYS = ("one", "two", "three", "four", "five")


@dataclass
class SpravBranch:
    """One branch of a chain, as the cabinet's branch list describes it."""

    # permanent_id: the Yandex Maps permalink, the join key to organizations.
    permanent_id: str
    sprav_id: str | None = None
    name: str | None = None
    address: str | None = None
    city: str | None = None
    region: str | None = None
    lat: float | None = None
    lon: float | None = None
    publishing_status: str | None = None
    rating: float | None = None
    review_count: int | None = None


@dataclass
class RatingPoint:
    """The chain's rating for one week, alongside the rivals Yandex compares it to."""

    week: date
    rating: float | None
    opponents: list[dict] = field(default_factory=list)


@dataclass
class RatingHistory:
    """A branch's rating history page.

    ``stars`` values and ``rating`` are ``None`` when the cabinet published no
    figure — never 0, which would be a real measurement.
    """

    history: list[RatingPoint] = field(default_factory=list)
    stars: dict[str, int | None] = field(default_factory=dict)
    card_strength: int | None = None
    factors: list[dict] = field(default_factory=list)


@dataclass
class ChainFetchResult:
    """Outcome of a cabinet read, in the same shape the other scrapers report."""

    branches: list[SpravBranch] = field(default_factory=list)
    total: int | None = None
    chain_name: str | None = None
    needs_manual_action: bool = False
    error_code: str | None = None
    error_message: str | None = None


def _dig(payload: object, path: tuple[str, ...]) -> object:
    """Walk a nested path, bailing out the moment the shape disagrees."""
    current = payload
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


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
        return int(value) if value == value and value not in (float("inf"), float("-inf")) else None
    return None


def _as_float(value: object) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        # json.loads accepts NaN/Infinity; neither is a rating.
        return float(value) if value == value and value not in (float("inf"), float("-inf")) else None
    return None


def _address_components(raw: dict) -> dict[str, str | None]:
    """Flatten address.components into the kinds we care about."""
    address = raw.get("address") if isinstance(raw.get("address"), dict) else {}
    formatted = address.get("formatted")
    if isinstance(formatted, dict):
        formatted = formatted.get("value")

    by_kind: dict[str, str | None] = {}
    for component in address.get("components") or []:
        if not isinstance(component, dict):
            continue
        name = component.get("name")
        if isinstance(name, dict):
            name = name.get("value")
        # Several components share a kind (province appears per admin level);
        # the first is the broadest, so keep it and ignore the rest.
        by_kind.setdefault(str(component.get("kind")), _as_str(name))

    coordinates = (address.get("pos") or {}).get("coordinates") if isinstance(address.get("pos"), dict) else None
    lon, lat = (coordinates + [None, None])[:2] if isinstance(coordinates, list) else (None, None)

    return {
        "address": _as_str(formatted),
        "city": by_kind.get("locality"),
        "region": by_kind.get("province"),
        "lon": _as_float(lon),
        "lat": _as_float(lat),
    }


def _parse_branch(raw: object) -> SpravBranch | None:
    if not isinstance(raw, dict) or raw.get("permanent_id") is None:
        return None
    parts = _address_components(raw)
    rating = raw.get("rating")
    return SpravBranch(
        permanent_id=str(raw["permanent_id"]),
        sprav_id=_as_str(str(raw["id"])) if raw.get("id") is not None else None,
        name=_as_str(raw.get("displayName")),
        address=parts["address"],
        city=parts["city"],
        region=parts["region"],
        lat=parts["lat"],
        lon=parts["lon"],
        publishing_status=_as_str(raw.get("publishing_status")),
        rating=_as_float(rating.get("score") if isinstance(rating, dict) else rating),
        review_count=_as_int(raw.get("reviewsCount")),
    )


def parse_chain_branches(preload: object) -> list[SpravBranch]:
    """Map one branch-list page to SpravBranch records.

    Degrades safely: any unexpected shape yields [] rather than raising.
    """
    raw_list = _dig(preload, _BRANCH_LIST_PATH)
    if not isinstance(raw_list, list):
        return []
    parsed = (_parse_branch(item) for item in raw_list)
    return [branch for branch in parsed if branch is not None]


def parse_branch_total(preload: object) -> int | None:
    """How many branches the cabinet says the filtered list holds."""
    pager = _dig(preload, _PAGER_PATH)
    return _as_int(pager.get("total")) if isinstance(pager, dict) else None


def parse_chain_name(preload: object) -> str | None:
    return _as_str(_dig(preload, _CHAIN_NAME_PATH))


def _week_to_date(micros: object) -> date | None:
    """`week` is a microsecond epoch marking the start of the week."""
    if not isinstance(micros, int) or isinstance(micros, bool):
        return None
    try:
        return datetime.fromtimestamp(micros / 1_000_000, tz=timezone.utc).date()
    except (OverflowError, OSError, ValueError):
        return None


def parse_rating_history(preload: object) -> RatingHistory:
    """Map a rating-history page to a RatingHistory.

    Degrades safely: an unexpected shape yields an empty RatingHistory.
    """
    data = _dig(preload, _RATING_HISTORY_PATH)
    result = RatingHistory()
    if isinstance(data, dict):
        statistic = data.get("rating_statistic")
        if isinstance(statistic, dict):
            result.stars = {key: _as_int(statistic.get(key)) for key in _STAR_KEYS}

        for raw in data.get("rating_history") or []:
            if not isinstance(raw, dict):
                continue
            week = _week_to_date(raw.get("week"))
            if week is None:
                continue
            result.history.append(
                RatingPoint(
                    week=week,
                    rating=_as_float(raw.get("rating")),
                    opponents=[
                        {
                            "name": _as_str(o.get("name")),
                            "permalink": _as_str(str(o["permalink"])) if o.get("permalink") is not None else None,
                            "rating": _as_float(o.get("rating")),
                        }
                        for o in raw.get("opponents_ratings") or []
                        if isinstance(o, dict)
                    ],
                )
            )

    factors = _dig(preload, _FACTORS_PATH)
    if isinstance(factors, dict):
        result.card_strength = _as_int(factors.get("strength"))
        result.factors = [
            {
                "name": _as_str(f.get("name")),
                "active": bool(f.get("active")),
                "strength": _as_int(f.get("strength")),
                "days_from_update": _as_int(f.get("days_from_update")),
                "status": _as_str(f.get("status")),
            }
            for f in factors.get("factors") or []
            if isinstance(f, dict)
        ]
    return result


def load_cabinet_cookies(storage_state_path: str) -> dict[str, str]:
    """Read the operator's yandex.ru cookies out of the Playwright storage state.

    Raises FileNotFoundError when no session has been saved yet — the caller
    turns that into needs_manual_action.
    """
    state = json.loads(Path(storage_state_path).read_text(encoding="utf-8"))
    return {
        cookie["name"]: cookie["value"]
        for cookie in state.get("cookies", [])
        if isinstance(cookie, dict) and str(cookie.get("domain", "")).endswith("yandex.ru")
    }


class SpravChainReader:
    """Browserless reader for the cabinet's chain pages.

    Holds one ``requests.Session`` carrying the operator cookies, and paces
    itself with ``settings.http_scrape_delay_seconds`` between pages the way the
    other scrapers do.
    """

    REQUEST_TIMEOUT_SECONDS = 60

    def __init__(self, storage_state_path: str | None = None) -> None:
        self.storage_state_path = storage_state_path or settings.yandex_storage_state_path
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": settings.http_scrape_user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
            }
        )
        self._authenticated = False

    def _authenticate(self) -> str | None:
        """Load cookies once. Returns an error code, or None on success."""
        if self._authenticated:
            return None
        path = Path(self.storage_state_path)
        if not path.exists() or path.stat().st_size == 0:
            return "missing_session"
        try:
            self.session.cookies.update(load_cabinet_cookies(str(path)))
        except (ValueError, OSError):
            return "missing_session"
        self._authenticated = True
        return None

    def _fetch(self, url: str) -> tuple[object | None, str | None]:
        """GET one cabinet page and return (preload, error_code)."""
        try:
            response = self.session.get(url, timeout=self.REQUEST_TIMEOUT_SECONDS)
        except requests.RequestException as exc:
            return None, f"request_failed:{type(exc).__name__}"

        # A redirect to Passport means the saved session no longer authenticates.
        if "passport.yandex" in response.url:
            return None, "session_expired"
        if response.status_code != 200:
            return None, f"http_{response.status_code}"

        lowered = response.text.lower()
        if any(marker.lower() in lowered for marker in BOT_MARKERS):
            return None, "access_challenge"
        return extract_preload_data(response.text), None

    def list_branches(self, chain_id: str, max_pages: int = 100) -> ChainFetchResult:
        """Page through a chain's branch list until the cabinet's total is reached."""
        error = self._authenticate()
        if error:
            return ChainFetchResult(
                needs_manual_action=True,
                error_code=error,
                error_message="No saved cabinet session — run: python -m scripts.sprav_login",
            )

        result = ChainFetchResult()
        seen: set[str] = set()
        for page in range(1, max_pages + 1):
            url = f"https://yandex.ru/sprav/chain/{chain_id}/branches?page={page}"
            preload, error = self._fetch(url)
            if error:
                result.error_code = error
                result.error_message = f"Failed on page {page} of chain {chain_id}"
                result.needs_manual_action = error in ("session_expired", "access_challenge", "missing_session")
                return result

            result.chain_name = result.chain_name or parse_chain_name(preload)
            result.total = parse_branch_total(preload) or result.total

            fresh = [b for b in parse_chain_branches(preload) if b.permanent_id not in seen]
            seen.update(b.permanent_id for b in fresh)
            result.branches.extend(fresh)

            # Stop on a page that added nothing new (the cabinet repeats the last
            # page past the end) or once the reported total is covered.
            if not fresh or (result.total is not None and len(result.branches) >= result.total):
                break
        return result

    def rating_history(self, permanent_id: str) -> tuple[RatingHistory | None, str | None]:
        """Read one branch's rating history. Returns (history, error_code)."""
        error = self._authenticate()
        if error:
            return None, error
        preload, error = self._fetch(f"https://yandex.ru/sprav/{permanent_id}/p/edit/rating-history/")
        if error:
            return None, error
        history = parse_rating_history(preload)
        if not history.history and not history.stars:
            return None, "rating_history_not_found"
        return history, None
