"""ScrapeOps.io proxy scraper for Yandex Maps reviews (scrapeops mode).

Sends the target Yandex URL to the ScrapeOps proxy API which handles
headers, fingerprinting, and geo-rotation. Returns rendered HTML which
is parsed by the shared ``parse_reviews_from_html`` (feature 002).

No captcha bypass: bot-protection pages → ``needs_manual_action`` with
a saved HTML debug artifact (constitution Principle IV).
"""

from __future__ import annotations

import re

import requests

from app.core.config import settings
from app.scraper.debug_artifacts import save_html_debug
from app.scraper.parser import parse_reviews_from_html
from app.scraper.types import ParsedOrganization, ParsedReview, ScrapeResult

PROXY_URL = "https://proxy.scrapeops.io/v1/"
BOT_MARKERS: tuple[str, ...] = (
    "Обнаружена защита от ботов",
    "showcaptcha",
    "SmartCaptcha",
    "Подтвердите, что запросы",
)


class YandexScrapeOpsScraper:
    REQUEST_TIMEOUT_SECONDS = 30

    def scrape(self, url: str) -> ScrapeResult:
        if not settings.scrapeops_api_key:
            return ScrapeResult(
                needs_manual_action=True,
                error_code="no_api_key",
                error_message="SCRAPEOPS_API_KEY not configured",
            )

        result = ScrapeResult()
        limit = settings.scrapeops_limit
        max_pages = settings.scrapeops_max_pages

        organization = ParsedOrganization()
        collected: list[ParsedReview] = []

        try:
            for page in range(1, max_pages + 1):
                if len(collected) >= limit:
                    break

                html, err = self._fetch(self._page_url(url, page))
                if err is not None:
                    return err
                if html is None:
                    if page == 1:
                        result.error_code = "fetch_error"
                        result.error_message = "Could not fetch the first review page"
                        return result
                    break

                if self._is_bot_wall(html):
                    result.needs_manual_action = True
                    result.error_code = "access_challenge"
                    result.error_message = "Bot protection / access challenge detected via ScrapeOps proxy"
                    result.debug_html = save_html_debug(html, "scrapeops-challenge")
                    return result

                org, reviews = parse_reviews_from_html(html)
                if page == 1:
                    organization = org
                if not reviews:
                    break
                collected.extend(reviews)

            result.organization = organization
            result.reviews = collected[:limit]
            return result
        except Exception as exc:
            result.error_code = "scrapeops_error"
            result.error_message = str(exc)
            return result

    def _fetch(self, url: str) -> tuple[str | None, ScrapeResult | None]:
        params = {
            "api_key": settings.scrapeops_api_key,
            "url": url,
            "render_js": "true" if settings.scrapeops_render_js else "false",
        }
        try:
            resp = requests.get(PROXY_URL, params=params, timeout=self.REQUEST_TIMEOUT_SECONDS)
            resp.raise_for_status()
            return resp.text, None
        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code in (401, 403):
                return None, ScrapeResult(
                    needs_manual_action=True,
                    error_code="invalid_api_key",
                    error_message=f"ScrapeOps rejected API key: HTTP {e.response.status_code}",
                )
            return None, ScrapeResult(
                error_code="http_error",
                error_message=str(e),
            )
        except requests.exceptions.RequestException as e:
            return None, ScrapeResult(
                error_code="network_error",
                error_message=str(e),
            )

    @staticmethod
    def _page_url(base_url: str, page: int) -> str:
        cleaned = re.sub(r"[?&]page=\d+", "", base_url)
        separator = "&" if "?" in cleaned else "?"
        return f"{cleaned}{separator}page={page}"

    @staticmethod
    def _is_bot_wall(html: str) -> bool:
        lowered = html.lower()
        return any(marker.lower() in lowered for marker in BOT_MARKERS)
