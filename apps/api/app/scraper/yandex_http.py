"""Browserless Yandex Maps review scraper (public_http mode).

Ported from the sibling BrandTrackerAI_Parser ``MultiPageYandexParser``: plain
``requests`` + pagination over ``?page=N``. Review extraction is delegated to the shared
``parse_reviews_from_html`` (feature 002); this scraper owns only fetching, pagination,
and bot-detection. Returns the standard ``ScrapeResult``.

No captcha bypass: a bot-protection / access challenge becomes ``needs_manual_action``
with a saved HTML debug artifact (constitution Principle IV).
"""

from __future__ import annotations

import re
import time

import requests

from app.core.config import settings
from app.scraper.debug_artifacts import save_html_debug
from app.scraper.parser import parse_reviews_from_html
from app.scraper.types import ParsedOrganization, ParsedReview, ScrapeResult
# More specific than CAPTCHA_MARKERS: exclude bare "captcha" which matches
# the `captchapgrd` fingerprinting library URL embedded in every Yandex Maps
# SPA page, producing false positives on normal review pages.
BOT_MARKERS: tuple[str, ...] = (
    "Обнаружена защита от ботов",
    "showcaptcha",
    "SmartCaptcha",
    "Подтвердите, что запросы",
)


class YandexHttpScraper:
    REQUEST_TIMEOUT_SECONDS = 10

    def __init__(self) -> None:
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

    def scrape(self, url: str) -> ScrapeResult:
        url = self._resolve_reviews_url(url)
        result = ScrapeResult()
        limit = settings.http_scrape_limit
        max_pages = settings.http_scrape_max_pages
        delay = settings.http_scrape_delay_seconds

        organization = ParsedOrganization()
        collected: list[ParsedReview] = []
        seen_keys: set[tuple[str | None, int, str]] = set()

        try:
            for page in range(1, max_pages + 1):
                if len(collected) >= limit:
                    break

                html = self._fetch(self._page_url(url, page))
                if html is None:
                    if page == 1:
                        result.error_code = "fetch_error"
                        result.error_message = "Could not fetch the first review page"
                        return result
                    continue  # skip a transient page error, keep what we have

                if self._is_bot_wall(html):
                    result.needs_manual_action = True
                    result.error_code = "access_challenge"
                    result.error_message = "Bot protection / access challenge detected"
                    result.debug_html = save_html_debug(html, "http-challenge")
                    return result

                org, reviews = parse_reviews_from_html(html)
                if page == 1:
                    organization = org

                fresh = 0
                for review in reviews:
                    key = (review.author_name, review.rating, review.review_text)
                    if key in seen_keys:
                        continue
                    seen_keys.add(key)
                    collected.append(review)
                    fresh += 1
                    if len(collected) >= limit:
                        break

                # No new reviews on a non-first page → assume pagination exhausted.
                if page > 1 and fresh == 0:
                    break

                if page < max_pages and delay > 0:
                    time.sleep(delay)

            result.organization = organization
            result.reviews = collected
            return result
        except Exception as exc:  # never raise out of a scrape attempt
            result.error_code = "http_scrape_error"
            result.error_message = str(exc)
            return result

    def _resolve_reviews_url(self, url: str) -> str:
        """Follow redirects and ensure the URL points to the reviews tab.

        Short links (/maps/-/...) and org root URLs lack /reviews/; fetching
        them returns the SPA shell without review blocks.
        """
        try:
            response = self.session.head(url, timeout=self.REQUEST_TIMEOUT_SECONDS, allow_redirects=True)
            resolved = response.url
        except requests.RequestException:
            resolved = url

        # Strip query/fragment to get the clean path, then re-append if reviews already there.
        base = re.split(r"[?#]", resolved)[0].rstrip("/")
        if "/reviews" not in base:
            base = f"{base}/reviews"
        return base + "/"

    def _fetch(self, url: str) -> str | None:
        """Download a page; return HTML, or None on network / non-200 error."""
        try:
            response = self.session.get(url, timeout=self.REQUEST_TIMEOUT_SECONDS)
            response.raise_for_status()
            return response.text
        except requests.RequestException:
            return None

    @staticmethod
    def _page_url(base_url: str, page: int) -> str:
        cleaned = re.sub(r"[?&]page=\d+", "", base_url)
        separator = "&" if "?" in cleaned else "?"
        return f"{cleaned}{separator}page={page}"

    @staticmethod
    def _is_bot_wall(html: str) -> bool:
        lowered = html.lower()
        return any(marker.lower() in lowered for marker in BOT_MARKERS)
