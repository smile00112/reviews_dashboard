import random
import time

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from app.scraper.debug_artifacts import save_debug_artifacts
from app.scraper.parser import parse_reviews_from_html
from app.scraper.types import ScrapeResult

CAPTCHA_MARKERS = ("captcha", "showcaptcha", "SmartCaptcha", "Подтвердите, что запросы")


class YandexPublicScraper:
    PAGE_LOAD_TIMEOUT_MS = 30_000
    MAX_SCROLLS = 40
    SCROLL_DELAY_MIN_MS = 800
    SCROLL_DELAY_MAX_MS = 1500

    def scrape(self, url: str) -> ScrapeResult:
        result = ScrapeResult()
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                page = browser.new_page()
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=self.PAGE_LOAD_TIMEOUT_MS)
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
        last_height = 0
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
            height = page.evaluate(
                """
                () => {
                    const panel = document.querySelector('.scroll__container')
                        || document.querySelector('[class*="reviews-list"]')
                        || document.body;
                    return panel.scrollHeight;
                }
                """
            )
            if height == last_height:
                break
            last_height = height
