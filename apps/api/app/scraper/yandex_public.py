import random
import re
import time

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from app.scraper.debug_artifacts import save_debug_artifacts
from app.scraper.parser import parse_reviews_from_html
from app.scraper.types import ScrapeResult

# Do NOT include a bare "captcha": it matches the `captchapgrd` fingerprinting
# library URL embedded in every Yandex Maps SPA page, so a normal, fully-loaded
# review page would false-positive as an access challenge. Use only the markers
# that appear on genuine captcha / bot-wall pages (mirrors yandex_http.BOT_MARKERS).
CAPTCHA_MARKERS = (
    "showcaptcha",
    "SmartCaptcha",
    "Подтвердите, что запросы",
    "Обнаружена защита от ботов",
)


class YandexPublicScraper:
    PAGE_LOAD_TIMEOUT_MS = 30_000
    MAX_SCROLLS = 40
    SCROLL_DELAY_MIN_MS = 800
    SCROLL_DELAY_MAX_MS = 1500
    # Force the Russian locale. yandex.ru geo-redirects to yandex.com (English UI),
    # which renders dates as "June 11" instead of "11 июня". Since review_date_text
    # feeds build_review_hash, an English date would produce a different content_hash
    # than the public_http path (which stays on yandex.ru) and silently re-insert
    # every review across modes. locale + Accept-Language keep dates Russian.
    LOCALE = "ru-RU"
    EXTRA_HTTP_HEADERS = {"Accept-Language": "ru-RU,ru;q=0.9"}

    def scrape(self, url: str) -> ScrapeResult:
        result = ScrapeResult()
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                context = browser.new_context(
                    locale=self.LOCALE, extra_http_headers=self.EXTRA_HTTP_HEADERS
                )
                page = context.new_page()
                try:
                    # Navigate to the raw URL first so short links (/maps/-/CODE)
                    # resolve via redirect to their real org URL. Appending
                    # /reviews/ to an unresolved short link 404s — the reviews
                    # path must be built from the resolved page.url below.
                    page.goto(url, wait_until="domcontentloaded", timeout=self.PAGE_LOAD_TIMEOUT_MS)
                    page.wait_for_timeout(2000)
                    html = page.content()

                    if self._is_access_challenge(html):
                        result.needs_manual_action = True
                        result.error_code = "access_challenge"
                        result.error_message = "Captcha or access challenge detected"
                        save_debug_artifacts(page, "challenge")
                        return result

                    if "/reviews" not in page.url:
                        page.goto(
                            self._reviews_url(page.url),
                            wait_until="domcontentloaded",
                            timeout=self.PAGE_LOAD_TIMEOUT_MS,
                        )
                        page.wait_for_timeout(2000)
                        html = page.content()
                        if self._is_access_challenge(html):
                            result.needs_manual_action = True
                            result.error_code = "access_challenge"
                            result.error_message = "Captcha or access challenge detected"
                            save_debug_artifacts(page, "challenge")
                            return result

                    self._open_reviews_tab(page)
                    self._scroll_reviews(page)
                    self._expand_reviews(page)

                    html = page.content()
                    if self._is_access_challenge(html):
                        result.needs_manual_action = True
                        result.error_code = "access_challenge"
                        result.error_message = "Captcha or access challenge detected during scroll"
                        save_debug_artifacts(page, "challenge-scroll")
                        return result

                    org, reviews = parse_reviews_from_html(html)
                    result.organization = org
                    result.reviews = reviews
                    return result
                except PlaywrightTimeoutError as exc:
                    screenshot, html_path = save_debug_artifacts(page, "timeout")
                    result.error_code = "timeout"
                    result.error_message = str(exc)
                    result.debug_screenshot = screenshot
                    result.debug_html = html_path
                    return result
                except Exception as exc:
                    screenshot, html_path = save_debug_artifacts(page, "error")
                    result.error_code = "scrape_error"
                    result.error_message = str(exc)
                    result.debug_screenshot = screenshot
                    result.debug_html = html_path
                    return result
                finally:
                    browser.close()
        except Exception as exc:
            result.error_code = "browser_error"
            result.error_message = str(exc)
            return result

    @staticmethod
    def _reviews_url(url: str) -> str:
        """Point a Yandex Maps org URL at its reviews tab.

        The org root only renders ~3 preview reviews; the full, infinite-scroll
        review list lives under ``/reviews/``. Clicking the "Отзывы" tab is
        locale-fragile (yandex.ru redirects to yandex.com → English "Reviews"),
        so navigate to the reviews path directly instead.
        """
        base = re.split(r"[?#]", url)[0].rstrip("/")
        if not base.endswith("/reviews"):
            base = f"{base}/reviews"
        return base + "/"

    def _is_access_challenge(self, html: str) -> bool:
        lower = html.lower()
        return any(marker.lower() in lower for marker in CAPTCHA_MARKERS)

    def _open_reviews_tab(self, page) -> None:
        selectors = [
            'button:has-text("Отзывы")',
            'a:has-text("Отзывы")',
            '[aria-label*="Отзывы"]',
        ]
        for selector in selectors:
            try:
                locator = page.locator(selector).first
                if locator.count() > 0:
                    locator.click(timeout=5000)
                    page.wait_for_timeout(1500)
                    return
            except Exception:
                continue

    def _scroll_reviews(self, page) -> None:
        """Scroll the reviews panel until the rendered review count stops growing.

        Yandex lazy-loads reviews in batches on scroll and keeps earlier ones
        mounted (no virtualization), so counting ``.business-review-view`` nodes
        is a reliable progress signal — more robust than ``scrollHeight``, which
        can plateau while a batch is still fetching. Stop after the count holds
        steady across ``STABLE_ROUNDS`` consecutive scrolls.
        """
        STABLE_ROUNDS = 3
        stable = 0
        last_count = -1
        for _ in range(self.MAX_SCROLLS):
            page.evaluate(
                """
                () => {
                    const panel = document.querySelector('.scroll__container')
                        || document.querySelector('[class*="reviews-list"]')
                        || document.body;
                    panel.scrollTop = panel.scrollHeight;
                }
                """
            )
            delay = random.randint(self.SCROLL_DELAY_MIN_MS, self.SCROLL_DELAY_MAX_MS)
            page.wait_for_timeout(delay)
            count = page.evaluate(
                "() => document.querySelectorAll('.business-review-view').length"
            )
            if count == last_count:
                stable += 1
                if stable >= STABLE_ROUNDS:
                    break
            else:
                stable = 0
            last_count = count

    def _expand_reviews(self, page) -> None:
        """Click every "Ещё" body expander so full review text enters the DOM.

        Long reviews are truncated behind a spoiler in the SPA — the collapsed
        text ends with "…Ещё" and the remainder is not in the DOM until expanded.
        Without this the Playwright ``review_text`` differs from the full text on
        the public_http path, yielding a different ``content_hash`` for the same
        review across scrape modes (silent re-insert). Only the review-body
        expander (``__expand``) is clicked, not the owner-comment one
        (``__comment-expand``). Best-effort: a failed click never aborts a scrape.
        """
        try:
            clicked = page.evaluate(
                """
                () => {
                    const els = document.querySelectorAll('.business-review-view__expand');
                    els.forEach(el => { try { el.click(); } catch (_) {} });
                    return els.length;
                }
                """
            )
            if clicked:
                page.wait_for_timeout(1000)
        except Exception:
            pass
