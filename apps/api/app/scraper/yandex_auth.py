from pathlib import Path

from playwright.sync_api import sync_playwright

from app.models.enums import SessionStatus
from app.scraper.debug_artifacts import save_debug_artifacts
from app.scraper.types import ScrapeResult
from app.scraper.yandex_public import CAPTCHA_MARKERS, YandexPublicScraper


class YandexAuthScraper:
    def login(self, login: str, password: str, storage_state_path: str) -> tuple[SessionStatus, str]:
        if not login or not password:
            return SessionStatus.missing, "YANDEX_OPERATOR_LOGIN and YANDEX_OPERATOR_PASSWORD must be set"

        path = Path(storage_state_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                context = browser.new_context()
                page = context.new_page()
                try:
                    page.goto("https://passport.yandex.ru/auth", wait_until="domcontentloaded", timeout=30000)
                    page.fill('input[name="login"]', login)
                    page.click('button[type="submit"]')
                    page.wait_for_timeout(1500)

                    html = page.content()
                    if any(marker.lower() in html.lower() for marker in CAPTCHA_MARKERS):
                        return SessionStatus.needs_manual_action, "Captcha detected during login — use headed browser locally"

                    page.fill('input[name="passwd"]', password)
                    page.click('button[type="submit"]')
                    page.wait_for_timeout(3000)

                    html = page.content()
                    if any(marker.lower() in html.lower() for marker in CAPTCHA_MARKERS):
                        return SessionStatus.needs_manual_action, "Captcha or 2FA required — complete manually"

                    if "passport.yandex" in page.url and "auth" in page.url:
                        return SessionStatus.needs_manual_action, "Login did not complete — check credentials or 2FA"

                    context.storage_state(path=str(path))
                    return SessionStatus.valid, "Login successful"
                finally:
                    browser.close()
        except Exception as exc:
            return SessionStatus.needs_manual_action, f"Login failed: {exc}"

    def check_session(self, storage_state_path: str) -> SessionStatus:
        path = Path(storage_state_path)
        if not path.exists() or path.stat().st_size == 0:
            return SessionStatus.missing
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                context = browser.new_context(storage_state=str(path))
                page = context.new_page()
                try:
                    page.goto("https://yandex.ru/maps/", wait_until="domcontentloaded", timeout=30000)
                    html = page.content()
                    if any(marker.lower() in html.lower() for marker in CAPTCHA_MARKERS):
                        return SessionStatus.needs_manual_action
                    return SessionStatus.valid
                finally:
                    browser.close()
        except Exception:
            return SessionStatus.expired

    @staticmethod
    def _challenge_result(public: YandexPublicScraper, page) -> ScrapeResult | None:
        """needs_manual_action result with debug artifacts when the page is a
        captcha/bot wall (same contract as the public scraper); else None."""
        if not public._is_access_challenge(page.content()):
            return None
        result = ScrapeResult()
        result.needs_manual_action = True
        result.error_code = "access_challenge"
        result.error_message = "Captcha or access challenge detected"
        result.debug_screenshot, result.debug_html = save_debug_artifacts(page, "auth-challenge")
        return result

    def scrape(self, url: str, storage_state_path: str) -> ScrapeResult:
        path = Path(storage_state_path)
        if not path.exists():
            result = ScrapeResult()
            result.needs_manual_action = True
            result.error_code = "missing_session"
            result.error_message = "Storage state file not found"
            return result

        public = YandexPublicScraper()
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                context = browser.new_context(
                    storage_state=str(path),
                    locale=public.LOCALE,
                    extra_http_headers=public.EXTRA_HTTP_HEADERS,
                )
                page = context.new_page()
                try:
                    # Raw goto first so short links (/maps/-/CODE) resolve via
                    # redirect; the reviews path is built from the resolved URL.
                    page.goto(url, wait_until="domcontentloaded", timeout=public.PAGE_LOAD_TIMEOUT_MS)
                    page.wait_for_timeout(2000)
                    challenge = self._challenge_result(public, page)
                    if challenge is not None:
                        return challenge
                    if "/reviews" not in page.url:
                        page.goto(public._reviews_url(page.url), wait_until="domcontentloaded", timeout=public.PAGE_LOAD_TIMEOUT_MS)
                        page.wait_for_timeout(2000)
                        # A challenge can appear only on the reviews navigation
                        # (same checkpoint the public scraper re-checks).
                        challenge = self._challenge_result(public, page)
                        if challenge is not None:
                            return challenge
                    public._open_reviews_tab(page)
                    challenge = self._challenge_result(public, page)
                    if challenge is not None:
                        return challenge
                    public._scroll_reviews(page)
                    public._expand_reviews(page)
                    from app.scraper.parser import parse_reviews_from_html

                    org, reviews = parse_reviews_from_html(page.content())
                    result = ScrapeResult(organization=org, reviews=reviews)
                    return result
                finally:
                    browser.close()
        except Exception as exc:
            result = ScrapeResult()
            result.error_code = "auth_scrape_error"
            result.error_message = str(exc)
            return result
