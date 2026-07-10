"""2GIS reviews API scraper (twogis_api mode, feature 006).

Collects org-level 2GIS reviews via public JSON APIs — no HTML parsing of the 2GIS
SPA, no captcha bypass:

  * ``catalog.api.2gis.com/3.0/items/byid``          — firm_id → org_id + name/rating/count
  * ``public-api.reviews.2gis.com/3.0/orgs/{id}/reviews`` — paginated reviews

A full ``…/firm/{id}`` URL yields firm_id with no network call. A ``go.2gis.com/CODE``
short link is bot-walled on a direct SPA fetch (HTTP 403 from a datacenter IP), so its
firm_id is resolved through the ScrapeOps proxy (feature 005). The 2GIS JSON APIs are
called directly, falling back to the ScrapeOps proxy on an IP-block. Blocked keys and
access challenges surface as ``needs_manual_action`` (constitution IV/VIII), never a
silent failure or bypass.

2GIS reviews are org-level: two branch short links of the same organization resolve to
the same ``org_id`` and the same review pool. That is the correct unit for this product.
"""

from __future__ import annotations

import re
import time
from collections import Counter

import requests

from app.core.config import settings
from app.scraper.debug_artifacts import save_html_debug
from app.scraper.normalize import normalize_review_date
from app.scraper.types import ParsedOrganization, ParsedReview, ScrapeResult

CATALOG_URL = "https://catalog.api.2gis.com/3.0/items/byid"
REVIEWS_URL = "https://public-api.reviews.2gis.com/3.0/orgs/{org_id}/reviews"
SCRAPEOPS_PROXY = "https://proxy.scrapeops.io/v1/"
FIRM_ID_RE = re.compile(r"/firm/(\d+)")
# Markers of a 2GIS bot wall / access challenge on the short-link HTML fetch. A bare
# "captcha" is intentionally excluded (it matches fingerprinting library URLs).
BOT_MARKERS: tuple[str, ...] = (
    "Обнаружена защита от ботов",
    "showcaptcha",
    "SmartCaptcha",
    "Доступ ограничен",
    "Access Denied",
)


class TwogisApiScraper:
    REQUEST_TIMEOUT_SECONDS = 30
    PROXY_TIMEOUT_SECONDS = 90

    def scrape(self, url: str, metrics_only: bool = False) -> ScrapeResult:
        result = ScrapeResult()
        try:
            firm_id, challenge = self._resolve_firm_id(url)
            if challenge is not None:
                return challenge
            if not firm_id:
                result.error_code = "twogis_no_firm_id"
                result.error_message = "Could not resolve a 2GIS firm id from the URL"
                return result

            org_id, organization, err = self._catalog_lookup(firm_id)
            if err is not None:
                return err

            result.organization = organization
            # catalog already carries rating/counts; skip the reviews pagination.
            result.reviews = [] if metrics_only else self._fetch_reviews(org_id)
            return result
        except Exception as exc:  # never raise out of a scrape attempt (constitution IV)
            result.error_code = "twogis_error"
            result.error_message = self._redact(str(exc))
            return result

    # --- firm id resolution -------------------------------------------------

    def _resolve_firm_id(self, url: str) -> tuple[str | None, ScrapeResult | None]:
        """Return (firm_id, challenge). A full ``/firm/{id}`` URL needs no network;
        a short link is resolved through the ScrapeOps proxy."""
        match = FIRM_ID_RE.search(url)
        if match:
            return match.group(1), None

        html, challenge = self._proxy_html(url)
        if challenge is not None:
            return None, challenge
        if not html:
            return None, None

        ids = FIRM_ID_RE.findall(html)
        if not ids:
            return None, None
        # The current firm's id dominates the page; foreign ids (ads, "similar")
        # appear less often. Most-common wins.
        firm_id = Counter(ids).most_common(1)[0][0]
        return firm_id, None

    def _proxy_html(self, url: str) -> tuple[str | None, ScrapeResult | None]:
        if not settings.scrapeops_api_key:
            return None, ScrapeResult(
                needs_manual_action=True,
                error_code="twogis_no_proxy_key",
                error_message="2GIS short-link resolution requires SCRAPEOPS_API_KEY; "
                "use a full …/firm/{id} URL instead",
            )
        try:
            resp = requests.get(
                SCRAPEOPS_PROXY,
                params={"api_key": settings.scrapeops_api_key, "url": url, "render_js": "false"},
                timeout=self.PROXY_TIMEOUT_SECONDS,
            )
            resp.raise_for_status()
            html = resp.text
        except requests.RequestException as exc:
            return None, ScrapeResult(
                error_code="twogis_proxy_error",
                error_message=self._redact(str(exc)),
            )
        if self._is_bot_wall(html):
            return None, ScrapeResult(
                needs_manual_action=True,
                error_code="access_challenge",
                error_message="2GIS bot protection during short-link resolution",
                debug_html=save_html_debug(html, "twogis-challenge"),
            )
        return html, None

    # --- catalog lookup (firm_id → org_id + metadata) -----------------------

    def _catalog_lookup(
        self, firm_id: str
    ) -> tuple[str | None, ParsedOrganization, ScrapeResult | None]:
        params = {
            "id": firm_id,
            "key": settings.twogis_catalog_key,
            "fields": "items.org,items.reviews,items.point,items.rubrics",
        }
        data, err = self._get_json(CATALOG_URL, params)
        if err is not None:
            return None, ParsedOrganization(), err

        meta = (data or {}).get("meta") or {}
        error = meta.get("error") or {}
        if meta.get("code") == 403 or error.get("type") == "apiKeyIsBlocked":
            return None, ParsedOrganization(), ScrapeResult(
                needs_manual_action=True,
                error_code="twogis_key_blocked",
                error_message="2GIS catalog key blocked — rotate TWOGIS_CATALOG_KEY",
            )

        items = ((data or {}).get("result") or {}).get("items") or []
        if not items:
            return None, ParsedOrganization(), ScrapeResult(
                error_code="twogis_firm_not_found",
                error_message=f"2GIS catalog returned no item for firm {firm_id}",
            )

        item = items[0]
        org = item.get("org") or {}
        reviews_meta = item.get("reviews") or {}
        organization = ParsedOrganization(
            name=item.get("name"),
            rating=reviews_meta.get("org_rating") or reviews_meta.get("general_rating"),
            # org_review_count = отзывы (with text); *_with_stars = оценки (all ratings).
            review_count=reviews_meta.get("org_review_count")
            or reviews_meta.get("general_review_count"),
            rating_count=reviews_meta.get("org_review_count_with_stars")
            or reviews_meta.get("general_review_count_with_stars"),
        )
        org_id = org.get("id")
        if not org_id:
            return None, organization, ScrapeResult(
                error_code="twogis_no_org_id",
                error_message=f"2GIS item {firm_id} has no org id",
            )
        return str(org_id), organization, None

    # --- reviews pagination -------------------------------------------------

    def _fetch_reviews(self, org_id: str) -> list[ParsedReview]:
        collected: list[ParsedReview] = []
        limit = settings.twogis_review_limit
        page_size = settings.twogis_page_size
        delay = settings.twogis_request_delay_seconds
        url = REVIEWS_URL.format(org_id=org_id)
        offset = 0

        while len(collected) < limit:
            params = {
                "key": settings.twogis_review_key,
                "limit": page_size,
                "offset": offset,
                "sort_by": "date_created",
                "rated": "true",
            }
            data, err = self._get_json(url, params)
            if err is not None or not data:
                break
            batch = data.get("reviews") or []
            if not batch:
                break
            for raw in batch:
                collected.append(self._map_review(raw))
                if len(collected) >= limit:
                    break
            if not ((data.get("meta") or {}).get("next_link")):
                break
            offset += page_size
            if delay > 0:
                time.sleep(delay)

        return collected

    @staticmethod
    def _map_review(raw: dict) -> ParsedReview:
        user = raw.get("user") or {}
        official = raw.get("official_answer")
        date_created = raw.get("date_created") or ""
        try:
            rating = int(raw.get("rating"))
        except (TypeError, ValueError):
            rating = 0
        review_id = raw.get("id")
        return ParsedReview(
            author_name=user.get("name"),
            rating=rating,
            review_text=raw.get("text") or "",
            # date_created is immutable per review → stable content_hash across re-scrapes.
            review_date_text=date_created or None,
            review_date=normalize_review_date(date_created[:10] if date_created else None),
            response_text=official.get("text") if isinstance(official, dict) else None,
            external_review_id=str(review_id) if review_id is not None else None,
        )

    # --- transport (direct + ScrapeOps fallback) ----------------------------

    def _get_json(self, url: str, params: dict) -> tuple[dict | None, ScrapeResult | None]:
        """Direct GET; on an IP-block (HTTP 403/429 or network error) retry through
        the ScrapeOps proxy. Body-level key errors are handled by the caller."""
        try:
            resp = requests.get(url, params=params, timeout=self.REQUEST_TIMEOUT_SECONDS)
            if resp.status_code in (403, 429):
                return self._get_json_via_proxy(url, params)
            resp.raise_for_status()
            return resp.json(), None
        except requests.RequestException:
            return self._get_json_via_proxy(url, params)
        except ValueError as exc:  # non-JSON body
            return None, ScrapeResult(
                error_code="twogis_bad_response",
                error_message=self._redact(str(exc)),
            )

    def _get_json_via_proxy(
        self, url: str, params: dict
    ) -> tuple[dict | None, ScrapeResult | None]:
        if not settings.scrapeops_api_key:
            return None, ScrapeResult(
                error_code="twogis_ip_blocked",
                error_message="2GIS API blocked and no SCRAPEOPS_API_KEY for fallback",
            )
        target = requests.Request("GET", url, params=params).prepare().url
        try:
            resp = requests.get(
                SCRAPEOPS_PROXY,
                params={"api_key": settings.scrapeops_api_key, "url": target, "render_js": "false"},
                timeout=self.PROXY_TIMEOUT_SECONDS,
            )
            resp.raise_for_status()
            return resp.json(), None
        except (requests.RequestException, ValueError) as exc:
            return None, ScrapeResult(
                error_code="twogis_proxy_error",
                error_message=self._redact(str(exc)),
            )

    # --- helpers ------------------------------------------------------------

    @staticmethod
    def _is_bot_wall(html: str) -> bool:
        lowered = html.lower()
        return any(marker.lower() in lowered for marker in BOT_MARKERS)

    @staticmethod
    def _redact(text: str) -> str:
        """Strip the ScrapeOps API key from any message that echoes the proxy URL
        (requests embeds the full URL in exception strings). Credentials must never
        leak into error_message or logs (CLAUDE.md / constitution VIII)."""
        key = settings.scrapeops_api_key
        return text.replace(key, "***") if key else text
