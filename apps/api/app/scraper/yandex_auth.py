from typing import Callable

from pathlib import Path

from playwright.sync_api import sync_playwright

from app.models.enums import SessionStatus
from app.scraper.debug_artifacts import save_debug_artifacts
from app.scraper.types import ScrapeResult
from app.scraper.yandex_public import CAPTCHA_MARKERS, YandexPublicScraper

# Passport routes the confirmation-code step to its own URL. Detecting the
# screen by URL rather than by page text is deliberate: "код из",
# "введите код" and "пароль" all live in Passport's bundled JS and match on
# EVERY screen (measured 6-26 hits each on the plain login screen), so text
# markers cannot tell the steps apart.
_CODE_SCREEN_URL_MARKER = "/auth/push-code"


def _is_code_screen(url: str | None) -> bool:
    """True once Passport has navigated to the confirmation-code step."""
    if not isinstance(url, str):
        return False
    return _CODE_SCREEN_URL_MARKER in url.lower()


class YandexAuthScraper:
    PASSPORT_AUTH_URL = "https://passport.yandex.ru/auth"
    # Session_id on a .yandex.ru domain is what Passport SSO hands out; it
    # authorizes Maps and the Sprav cabinet alike.
    SESSION_COOKIE = "Session_id"
    MANUAL_LOGIN_TIMEOUT_MS = 180000
    MANUAL_LOGIN_POLL_MS = 1000
    LOGIN_PLACEHOLDER = "Логин или email"
    NEXT_BUTTON_TEXT = "Далее"
    CONTINUE_BUTTON_TEXT = "Продолжить"
    # Passport defaults to passwordless (its URLs are /pwl-yandex/...): after
    # the login step it goes straight to a push code. This button is the way
    # back to the password screen.
    PASSWORD_BUTTON_TEXT = "Войти с паролем"
    # Short probes, because these elements are optional by design — a missing
    # one is a branch to take, not an error to wait 30s for.
    PROBE_TIMEOUT_MS = 5000
    SETTLE_MS = 3000

    def login(
        self,
        login: str,
        password: str,
        storage_state_path: str,
    ) -> tuple[SessionStatus, str]:
        """Automated login with credentials. Kept for the API path
        (ScrapeService.login_operator) and currently STALE: Passport serves a
        React passwordless flow whose login field has no name= and a generated
        id, so these selectors no longer match and this returns
        needs_manual_action. Console users want login_manual() instead.
        """
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

    @staticmethod
    def _has_session_cookie(cookies: list[dict]) -> bool:
        """True once Passport has issued a session cookie for yandex.ru."""
        return any(
            cookie.get("name") == YandexAuthScraper.SESSION_COOKIE
            and cookie.get("value")
            and "yandex.ru" in (cookie.get("domain") or "")
            for cookie in cookies
        )

    def _passport_challenge(self, page) -> tuple[SessionStatus, str] | None:
        """Bot-wall/captcha check at a login checkpoint — same markers as the
        rest of the codebase, never bypassed."""
        html = page.content()
        if any(marker.lower() in html.lower() for marker in CAPTCHA_MARKERS):
            return SessionStatus.needs_manual_action, "Captcha or bot check detected during login"
        return None

    @staticmethod
    def _fill_code(page, code: str) -> None:
        """Passport renders the confirmation code as one box per digit (six of
        them, observed live), but has used a single input before; fill
        whichever is present."""
        boxes = [
            box
            for box in page.locator('input[type="tel"], input[type="text"], input[type="number"]').all()
            if box.is_visible()
        ]
        if len(boxes) >= len(code):
            for digit, box in zip(code, boxes):
                box.fill(digit)
        elif boxes:
            boxes[0].fill(code)

    def _try_password_step(self, page, password: str) -> bool:
        """Switch Passport off its passwordless default and submit the
        password. Returns False (without raising) whenever that route isn't
        offered — the caller then finishes via the confirmation code."""
        try:
            switch = page.get_by_role("button", name=self.PASSWORD_BUTTON_TEXT)
            if switch.count() and switch.first.is_visible():
                switch.first.click()
                page.wait_for_timeout(self.SETTLE_MS)
        except Exception:
            return False

        try:
            field = page.locator('input[type="password"]').first
            field.wait_for(state="visible", timeout=self.PROBE_TIMEOUT_MS)
            field.fill(password)
        except Exception:
            return False

        for label in (self.NEXT_BUTTON_TEXT, self.CONTINUE_BUTTON_TEXT):
            try:
                button = page.get_by_role("button", name=label)
                if button.count() and button.first.is_visible():
                    button.first.click()
                    page.wait_for_timeout(self.SETTLE_MS)
                    return True
            except Exception:
                continue
        return False

    def login_with_password(
        self,
        login: str,
        password: str,
        storage_state_path: str,
        request_code: Callable[[], str | None] | None = None,
    ) -> tuple[SessionStatus, str]:
        """Automated password + confirmation-code login (Yandex
        password+confirmation-code login). Uses resilient text/role locators
        rather than name=/id selectors — Passport's React flow regenerates
        those per render, which is why the older `login()` method above no
        longer works. `request_code` is called once a confirmation-code
        screen appears; it blocks until the operator submits one (or times
        out) and is owned entirely by the caller — this method never touches
        the database."""
        if not login or not password:
            return SessionStatus.missing, "YANDEX_OPERATOR_LOGIN and YANDEX_OPERATOR_PASSWORD must be set"

        path = Path(storage_state_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                context = browser.new_context(locale=YandexPublicScraper.LOCALE)
                page = context.new_page()
                try:
                    page.goto(self.PASSPORT_AUTH_URL, wait_until="domcontentloaded", timeout=30000)

                    challenge = self._passport_challenge(page)
                    if challenge:
                        return challenge

                    page.get_by_placeholder(self.LOGIN_PLACEHOLDER).fill(login)
                    page.get_by_role("button", name=self.NEXT_BUTTON_TEXT).click()
                    page.wait_for_timeout(self.SETTLE_MS)

                    challenge = self._passport_challenge(page)
                    if challenge:
                        return challenge

                    # Password first when Passport still offers it; otherwise
                    # fall through to the confirmation code it sent instead.
                    self._try_password_step(page, password)

                    challenge = self._passport_challenge(page)
                    if challenge:
                        return challenge

                    if not self._has_session_cookie(context.cookies()) and _is_code_screen(page.url):
                        if request_code is None:
                            return (
                                SessionStatus.needs_manual_action,
                                "Confirmation code required but no code channel was configured",
                            )
                        code = request_code()
                        if not code:
                            return SessionStatus.needs_manual_action, "Timed out waiting for the confirmation code"

                        self._fill_code(page, code)
                        page.get_by_role("button", name=self.CONTINUE_BUTTON_TEXT).first.click()
                        page.wait_for_timeout(self.SETTLE_MS)

                        challenge = self._passport_challenge(page)
                        if challenge:
                            return challenge

                    if self._has_session_cookie(context.cookies()):
                        context.storage_state(path=str(path))
                        return SessionStatus.valid, "Login successful"

                    return SessionStatus.needs_manual_action, "Login did not complete — no session cookie was issued"
                finally:
                    browser.close()
        except Exception as exc:
            return SessionStatus.needs_manual_action, f"Automated login failed: {exc}"

    def login_manual(
        self,
        storage_state_path: str,
        timeout_ms: int | None = None,
    ) -> tuple[SessionStatus, str]:
        """Open Passport in a visible browser; the operator signs in by hand.

        Fills nothing. Passport's React flow generates its input ids per render,
        so any hardcoded selector goes stale — and 2FA/QR cannot be automated
        anyway (constitution: no captcha/2FA bypass). Polling for the session
        cookie is independent of the markup and of which method the operator
        used to sign in.
        """
        path = Path(storage_state_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        deadline_ms = timeout_ms if timeout_ms is not None else self.MANUAL_LOGIN_TIMEOUT_MS

        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=False)
                context = browser.new_context(locale=YandexPublicScraper.LOCALE)
                page = context.new_page()
                try:
                    page.goto(self.PASSPORT_AUTH_URL, wait_until="domcontentloaded", timeout=30000)
                    waited_ms = 0
                    while waited_ms < deadline_ms:
                        if self._has_session_cookie(context.cookies()):
                            context.storage_state(path=str(path))
                            return SessionStatus.valid, "Login successful (manual)"
                        page.wait_for_timeout(self.MANUAL_LOGIN_POLL_MS)
                        waited_ms += self.MANUAL_LOGIN_POLL_MS
                    return SessionStatus.needs_manual_action, "Manual login not completed within the timeout"
                finally:
                    browser.close()
        except Exception as exc:
            return SessionStatus.needs_manual_action, f"Manual login failed: {exc}"

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
    def _challenge_result(public: YandexPublicScraper, page, response=None) -> ScrapeResult | None:
        """needs_manual_action result with debug artifacts when the page is a
        captcha/bot wall or an HTTP error status (same contract as the public
        scraper); else None."""
        if not (public._is_blocked_status(response) or public._is_access_challenge(page.content())):
            return None
        result = ScrapeResult()
        result.needs_manual_action = True
        result.error_code = "access_challenge"
        result.error_message = public._challenge_message(response)
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
                    response = page.goto(url, wait_until="domcontentloaded", timeout=public.PAGE_LOAD_TIMEOUT_MS)
                    page.wait_for_timeout(2000)
                    challenge = self._challenge_result(public, page, response)
                    if challenge is not None:
                        return challenge
                    if "/reviews" not in page.url:
                        response = page.goto(public._reviews_url(page.url), wait_until="domcontentloaded", timeout=public.PAGE_LOAD_TIMEOUT_MS)
                        page.wait_for_timeout(2000)
                        # A challenge can appear only on the reviews navigation
                        # (same checkpoint the public scraper re-checks).
                        challenge = self._challenge_result(public, page, response)
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
