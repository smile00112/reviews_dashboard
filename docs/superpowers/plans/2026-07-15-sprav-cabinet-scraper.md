# Yandex Sprav Cabinet Scraper Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Read the list of organizations the operator manages from the Yandex Business cabinet (`https://yandex.ru/sprav/`), driven from two console commands, using the storage-state session the project already produces.

**Architecture:** A Playwright context loaded with the existing operator storage-state opens the cabinet and reads the organization list out of the `window.__PRELOAD_DATA` state the page inlines (Task 2 established there is no companies XHR). I/O lives in `YandexSpravScraper`; parsing lives in pure `extract_preload_data` / `parse_sprav_orgs` functions that are the only unit-tested pieces. Two operator CLIs (`sprav_login`, `sprav_orgs`) drive it. Nothing is written to the database.

**Reality check (Task 2, live):** the cabinet lists **chains** (2 of them, 357 and 2 branches), not individual branches, and carries **no rating or review data at all**. Ratings/reviews remain the existing Maps scrapers' job. See the design spec's "Confirmed cabinet payload" section.

**Tech Stack:** Python 3, Playwright (sync API), pydantic-settings, pytest, argparse.

Design spec: `docs/superpowers/specs/2026-07-15-sprav-cabinet-scraper-design.md`

## Global Constraints

- **Read-only.** GET/read only against the cabinet. Never publish, edit, or delete anything on Yandex. Constitution hard rule.
- **No captcha bypass.** Captcha wall or redirect to `passport.yandex.ru` → `needs_manual_action` + debug artifacts. Never a silent retry, never a generic failure.
- **Credentials only in env.** `YANDEX_OPERATOR_LOGIN` / `YANDEX_OPERATOR_PASSWORD`. Storage-state stays under gitignored `.local/`. Never log, print, or return cookie values or credentials.
- **Session file is shared, not new.** Reuse `settings.yandex_storage_state_path`. Do not introduce a second session file.
- **Layering.** Scraper I/O in `app/scraper/`, pure parsing beside it with no I/O and no DB. Do not touch `app/api/` or `app/services/` in this feature.
- **No live-network tests.** Playwright I/O is not mocked and not exercised in CI; only pure functions are tested.
- **Backwards compatibility.** `YandexAuthScraper.login`'s existing call site (`ScrapeService.login_operator`) must keep working unchanged.

All work happens on branch `feature/011-sprav-cabinet`. All commands run from `apps/api/`.

---

## File Structure

| File | Responsibility |
|---|---|
| `apps/api/app/scraper/yandex_auth.py` (modify) | Adds `login_manual` + `_has_session_cookie`; `login()` left unchanged and stale. |
| `apps/api/app/scraper/yandex_sprav.py` (create) | `SpravOrg`, `SpravListResult`, pure `parse_sprav_orgs`, and the `YandexSpravScraper` Playwright I/O class. |
| `apps/api/app/core/config.py` (modify) | `sprav_companies_url`, `sprav_orgs_output_path`, `sprav_page_timeout_ms`. |
| `apps/api/scripts/sprav_login.py` (create) | Auth test command. |
| `apps/api/scripts/sprav_orgs.py` (create) | Org-list command: JSON to stdout + file. |
| `apps/api/tests/test_sprav_login_cli.py` (create) | Exit-code mapping + no-credentials short circuit. |
| `apps/api/tests/test_sprav_parser.py` (create) | `parse_sprav_orgs` happy path + degenerate inputs. |
| `apps/api/tests/test_sprav_scraper.py` (create) | Missing-session short circuit + challenge detection. |
| `apps/api/tests/test_sprav_orgs_cli.py` (create) | Serialization + exit-code mapping for the org-list command. |
| `apps/api/tests/fixtures/sprav_companies_preload.json` (created in Task 2) | The cabinet's inlined state, cut down to `initialState.companiesList` and scrubbed: business name/address/site only, zero tokens or personal data. |

Parser and scraper share one module because they change together (a payload shape change touches both) and the module stays small. This mirrors `yandex_http.py`, which delegates to a parser but keeps its own transport concerns local.

---

### Task 1: `headless` parameter + `sprav_login` command

> **⚠️ Partially superseded by Task 1a.** Implemented as written (commit `f175842`), then disproved against the live Passport: the headless auto-login this task builds cannot work, because Passport's selectors are stale. Task 1a reverts the `headless` parameter and replaces auto-login with a manual headed flow. The surviving parts of this task are the `sprav_login` CLI skeleton and `exit_code_for`. Read Task 1a before touching this code.

Threads a `headless` flag through the existing login and adds the operator command that exercises it. Default stays `True`, so the API login path is untouched.

**Files:**
- Modify: `apps/api/app/scraper/yandex_auth.py:12-50`
- Create: `apps/api/scripts/sprav_login.py`
- Test: `apps/api/tests/test_sprav_login_cli.py`

**Interfaces:**
- Consumes: `YandexAuthScraper.login(login, password, storage_state_path)`, `SessionStatus` from `app.models.enums`.
- Produces:
  - `YandexAuthScraper.login(login: str, password: str, storage_state_path: str, headless: bool = True) -> tuple[SessionStatus, str]`
  - `scripts.sprav_login.exit_code_for(status: SessionStatus) -> int`

- [ ] **Step 1: Write the failing test**

Create `apps/api/tests/test_sprav_login_cli.py`:

```python
"""Sprav auth CLI: exit-code contract and the no-credentials short circuit."""

import pytest

from app.models.enums import SessionStatus
from app.scraper.yandex_auth import YandexAuthScraper
from scripts.sprav_login import exit_code_for


@pytest.mark.parametrize("status,expected", [
    (SessionStatus.valid, 0),
    (SessionStatus.needs_manual_action, 2),
    (SessionStatus.missing, 1),
    (SessionStatus.expired, 1),
])
def test_exit_code_for(status, expected):
    assert exit_code_for(status) == expected


def test_login_without_credentials_short_circuits(tmp_path):
    """No creds must not launch a browser — it returns `missing` immediately."""
    status, message = YandexAuthScraper().login("", "", str(tmp_path / "state.json"))
    assert status == SessionStatus.missing
    assert "YANDEX_OPERATOR_LOGIN" in message


def test_login_accepts_headless_flag(tmp_path):
    """The new parameter is keyword-compatible and does not change the
    no-credentials contract."""
    status, _ = YandexAuthScraper().login("", "", str(tmp_path / "state.json"), headless=False)
    assert status == SessionStatus.missing
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_sprav_login_cli.py -v`

Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.sprav_login'`.

- [ ] **Step 3: Add the `headless` parameter**

In `apps/api/app/scraper/yandex_auth.py`, change the `login` signature and browser launch. Replace lines 12-13:

```python
class YandexAuthScraper:
    # A headed login is the escape hatch for 2FA/captcha: the operator finishes
    # the challenge by hand and we wait for Passport to hand off. Headless
    # auto-login cannot pass either and honestly reports needs_manual_action.
    MANUAL_LOGIN_TIMEOUT_MS = 180000

    def login(
        self,
        login: str,
        password: str,
        storage_state_path: str,
        headless: bool = True,
    ) -> tuple[SessionStatus, str]:
```

Change the launch (line 21):

```python
                browser = playwright.chromium.launch(headless=headless)
```

Then, in the `try:` block, replace the post-password block (lines 36-46) with:

```python
                    page.wait_for_timeout(3000)

                    if not headless:
                        # Operator completes 2FA/captcha in the visible window.
                        try:
                            page.wait_for_url(
                                lambda url: "passport.yandex" not in url,
                                timeout=self.MANUAL_LOGIN_TIMEOUT_MS,
                            )
                        except Exception:
                            return (
                                SessionStatus.needs_manual_action,
                                "Manual login not completed within the timeout",
                            )
                        context.storage_state(path=str(path))
                        return SessionStatus.valid, "Login successful (manual)"

                    html = page.content()
                    if any(marker.lower() in html.lower() for marker in CAPTCHA_MARKERS):
                        return SessionStatus.needs_manual_action, "Captcha or 2FA required — complete manually"

                    if "passport.yandex" in page.url and "auth" in page.url:
                        return SessionStatus.needs_manual_action, "Login did not complete — check credentials or 2FA"

                    context.storage_state(path=str(path))
                    return SessionStatus.valid, "Login successful"
```

- [ ] **Step 4: Write the CLI**

Create `apps/api/scripts/sprav_login.py`:

```python
"""Authorize the Yandex operator session and report the outcome.

Test/diagnostic command for the Sprav cabinet scraper. Deliberately does NOT
touch the database — it exercises only the login path and the storage-state file.

  python -m scripts.sprav_login             # headless auto-login with env creds
  python -m scripts.sprav_login --headed    # visible browser, operator does 2FA
  python -m scripts.sprav_login --check     # only verify the saved session

Exit codes: 0 valid, 2 needs_manual_action, 1 missing/expired.
"""

from __future__ import annotations

import argparse
import sys

from app.core.config import settings
from app.models.enums import SessionStatus
from app.scraper.yandex_auth import YandexAuthScraper

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_MANUAL = 2


def exit_code_for(status: SessionStatus) -> int:
    if status == SessionStatus.valid:
        return EXIT_OK
    if status == SessionStatus.needs_manual_action:
        return EXIT_MANUAL
    return EXIT_ERROR


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Authorize / check the Yandex operator session.")
    parser.add_argument("--check", action="store_true", help="Only check the saved session, do not log in.")
    parser.add_argument("--headed", action="store_true", help="Visible browser so the operator can pass 2FA/captcha.")
    args = parser.parse_args(argv)

    path = settings.yandex_storage_state_path
    scraper = YandexAuthScraper()

    if args.check:
        status = scraper.check_session(path)
        message = "checked saved session"
    else:
        status, message = scraper.login(
            settings.yandex_operator_login,
            settings.yandex_operator_password,
            path,
            headless=not args.headed,
        )

    # Never print the storage-state contents — only its path.
    print(f"status:  {status.value}")
    print(f"message: {message}")
    print(f"session: {path}")

    if status == SessionStatus.needs_manual_action and not args.headed:
        print("hint:    2FA/captcha likely — retry with: python -m scripts.sprav_login --headed", file=sys.stderr)

    return exit_code_for(status)


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_sprav_login_cli.py -v`

Expected: PASS (4 passed).

- [ ] **Step 6: Verify the existing auth tests still pass**

Run: `pytest tests/test_yandex_auth_scraper.py tests/test_scraper_session_async.py -v`

Expected: PASS — the `headless` default preserves the old behaviour.

- [ ] **Step 7: Commit**

```bash
git add app/scraper/yandex_auth.py scripts/sprav_login.py tests/test_sprav_login_cli.py
git commit -m "feat: sprav_login command and headless flag on operator login"
```

---

### Task 1a: Rework login to a manual headed flow (supersedes Task 1's headless auto-login)

**Why this exists.** Task 1 shipped headless auto-login as the default, per the user's choice at brainstorming time. Running it against the live Passport disproved that choice. Evidence gathered 2026-07-15:

```
GET https://passport.yandex.ru/auth
  → redirects to https://passport.yandex.ru/pwl-yandex/auth/add?cause=auth&process_uuid=…
  bot markers hit: none        (not a bot wall — the page loaded fully, 139 KB)
  input name=None id='react-aria-«R166b»' type='text' placeholder='Логин или email'
  buttons: 'Войти'  'Не помню пароль'  'QR-код'
```

Passport now serves a React passwordless (`pwl`) flow. There is **no** `input[name="login"]`; the login field has no `name` at all and its `id` is generated per render (`react-aria-«R166b»`), so it is unstable across loads. `login()`'s hardcoded selectors cannot match — the failure is `Page.fill: Timeout 30000ms exceeded waiting for locator("input[name=\"login\"]")`. This is a pre-existing bug in `login()`, not a regression from Task 1.

**Decision (user, 2026-07-15):** drop auto-login; the operator signs in by hand. Any selector we hardcode against this flow goes stale on Yandex's next redesign, and repeated automated login attempts risk tripping antifraud on a real account.

**Scope decision (controller):** do **not** modify the existing `login()`. It is called by `ScrapeService.login_operator` behind the `/api/scraper/yandex/login` endpoint, which runs server-side where a headed browser is impossible — repairing that path is a separate concern from this console-only feature. Add `login_manual()` alongside it, revert Task 1's `headless` parameter, and leave an honest docstring note on `login()`. This keeps the global constraint "do not touch `app/api/` or `app/services/`" intact.

**Files:**
- Modify: `apps/api/app/scraper/yandex_auth.py`
- Modify: `apps/api/scripts/sprav_login.py`
- Test: `apps/api/tests/test_sprav_login_cli.py`

**Interfaces:**
- Consumes: `SessionStatus` from `app.models.enums`; `YandexPublicScraper.LOCALE`.
- Produces:
  - `YandexAuthScraper.login_manual(storage_state_path: str, timeout_ms: int | None = None) -> tuple[SessionStatus, str]`
  - `YandexAuthScraper._has_session_cookie(cookies: list[dict]) -> bool` (static, pure — the tested seam)
  - `YandexAuthScraper.SESSION_COOKIE = "Session_id"`
  - `login()` reverts to its pre-branch signature: `login(self, login: str, password: str, storage_state_path: str) -> tuple[SessionStatus, str]`

- [ ] **Step 1: Write the failing test**

Replace the two `headless`-flag tests in `apps/api/tests/test_sprav_login_cli.py` (they test a flow that no longer exists) with cookie-seam tests. Keep the existing `test_exit_code_for` and `test_login_without_credentials_short_circuits` tests as they are.

```python
def test_session_cookie_present_is_detected():
    cookies = [
        {"name": "yandexuid", "value": "123", "domain": ".yandex.ru"},
        {"name": "Session_id", "value": "3:abc", "domain": ".yandex.ru"},
    ]
    assert YandexAuthScraper._has_session_cookie(cookies) is True


def test_no_cookies_is_not_logged_in():
    assert YandexAuthScraper._has_session_cookie([]) is False


def test_other_cookies_alone_are_not_a_session():
    cookies = [{"name": "yandexuid", "value": "123", "domain": ".yandex.ru"}]
    assert YandexAuthScraper._has_session_cookie(cookies) is False


def test_empty_session_value_is_not_a_session():
    cookies = [{"name": "Session_id", "value": "", "domain": ".yandex.ru"}]
    assert YandexAuthScraper._has_session_cookie(cookies) is False


def test_session_cookie_on_a_foreign_domain_is_ignored():
    cookies = [{"name": "Session_id", "value": "3:abc", "domain": ".example.com"}]
    assert YandexAuthScraper._has_session_cookie(cookies) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_sprav_login_cli.py -v`

Expected: FAIL — `AttributeError: type object 'YandexAuthScraper' has no attribute '_has_session_cookie'`.

- [ ] **Step 3: Revert the `headless` parameter from `login()` and note its staleness**

In `apps/api/app/scraper/yandex_auth.py`, restore `login` to its pre-branch form — signature `login(self, login: str, password: str, storage_state_path: str)`, `launch(headless=True)`, and delete the `if not headless:` manual branch added by Task 1. Add this docstring as the method's first statement:

```python
        """Automated login with credentials. Kept for the API path
        (ScrapeService.login_operator) and currently STALE: Passport serves a
        React passwordless flow whose login field has no name= and a generated
        id, so these selectors no longer match and this returns
        needs_manual_action. Console users want login_manual() instead.
        """
```

- [ ] **Step 4: Add the manual login**

In `apps/api/app/scraper/yandex_auth.py`, replace the `MANUAL_LOGIN_TIMEOUT_MS` class attribute block with:

```python
class YandexAuthScraper:
    PASSPORT_AUTH_URL = "https://passport.yandex.ru/auth"
    # Session_id on a .yandex.ru domain is what Passport SSO hands out; it
    # authorizes Maps and the Sprav cabinet alike.
    SESSION_COOKIE = "Session_id"
    MANUAL_LOGIN_TIMEOUT_MS = 180000
    MANUAL_LOGIN_POLL_MS = 1000
```

Add these two methods to the class:

```python
    @staticmethod
    def _has_session_cookie(cookies: list[dict]) -> bool:
        """True once Passport has issued a session cookie for yandex.ru."""
        return any(
            cookie.get("name") == YandexAuthScraper.SESSION_COOKIE
            and cookie.get("value")
            and "yandex.ru" in (cookie.get("domain") or "")
            for cookie in cookies
        )

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
```

- [ ] **Step 5: Point the CLI at the manual login**

In `apps/api/scripts/sprav_login.py`: drop the `--headed` argument (the login is always headed now), and replace the login branch of `main` so the default action is the manual login. The `--check` branch and `exit_code_for` are unchanged.

```python
    if args.check:
        status = scraper.check_session(path)
        message = "checked saved session"
    else:
        print("Opening Yandex Passport — sign in by hand in the browser window.", file=sys.stderr)
        print("Waiting for the session cookie…", file=sys.stderr)
        status, message = scraper.login_manual(path)
```

Update the module docstring's usage block to:

```
  python -m scripts.sprav_login           # opens a browser; operator signs in by hand
  python -m scripts.sprav_login --check   # only verify the saved session
```

Remove the now-unreachable `--headed` hint line at the end of `main`. Credentials are no longer read by this command; drop the `settings.yandex_operator_login` / `settings.yandex_operator_password` references from it.

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_sprav_login_cli.py tests/test_yandex_auth_scraper.py tests/test_scraper_session_async.py -v`

Expected: PASS. `test_login_without_credentials_short_circuits` still passes because `login()`'s credential guard is unchanged.

- [ ] **Step 7: Commit**

```bash
git add app/scraper/yandex_auth.py scripts/sprav_login.py tests/test_sprav_login_cli.py
git commit -m "fix: manual headed login — Passport's React flow broke auto-login selectors"
```

---

### Task 2: Discovery spike — capture the real cabinet payload

**This is an exploratory task, not a TDD task.** Its deliverable is knowledge plus a fixture. Tasks 3-5 depend on it; do not guess the payload shape ahead of it.

**Files:**
- Create: `apps/api/tests/fixtures/sprav_orgs_response.json`
- Modify: `docs/superpowers/specs/2026-07-15-sprav-cabinet-scraper-design.md` (record the confirmed endpoint + shape)

**Interfaces:**
- Consumes: `python -m scripts.sprav_login` from Task 1 (a valid session must exist first).
- Produces: the fixture file, and the confirmed answers to: (a) the companies-list request URL, (b) whether the list is XHR-fetched or server-rendered, (c) the JSON path to the organization array, (d) the field names for id/name/address/rating/reviews count.

- [ ] **Step 1: Establish a session**

Run: `python -m scripts.sprav_login` — a browser window opens; sign in by hand (password, QR, or 2FA — whatever the account uses).

Expected: `status: valid` and `.local/yandex-storage-state.json` exists and is non-empty.

- [ ] **Step 2: Open the cabinet with that session and record traffic**

Write a throwaway script at `apps/api/.local/discover_sprav.py` (under gitignored `.local/`, deleted in Step 5):

```python
"""Throwaway: dump cabinet network traffic to find the companies-list request."""

import json
from pathlib import Path

from playwright.sync_api import sync_playwright

from app.core.config import settings

OUT = Path(".local/sprav-capture")
OUT.mkdir(parents=True, exist_ok=True)
seen = []

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    context = browser.new_context(storage_state=settings.yandex_storage_state_path, locale="ru-RU")
    page = context.new_page()

    def on_response(response):
        ctype = response.headers.get("content-type", "")
        if "json" not in ctype:
            return
        try:
            body = response.json()
        except Exception:
            return
        seen.append(response.url)
        name = str(len(seen)).zfill(3) + ".json"
        (OUT / name).write_text(
            json.dumps({"url": response.url, "body": body}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    page.on("response", on_response)
    page.goto("https://yandex.ru/sprav/", wait_until="networkidle", timeout=60000)
    page.wait_for_timeout(5000)
    print(f"page url: {page.url}")
    print(f"captured {len(seen)} json responses in {OUT}")
    for u in seen:
        print(" -", u)
    input("Press Enter to close…")
    browser.close()
```

Run: `python .local/discover_sprav.py`

- [ ] **Step 3: Identify the companies response**

Inspect the dumped files in `.local/sprav-capture/`. Find the response containing the organization list.

Record for the spec:
- the request URL (parameterized parts noted),
- the JSON path to the array,
- the field names for id / name / address / rating / reviews count.

**If `page.url` redirected to `passport.yandex.ru`:** the session is not valid for the cabinet — stop and re-run Task 2 Step 1. Do not proceed on a guess.

**If no JSON response contains the list:** the cabinet server-renders it. Save `page.content()` to `apps/api/tests/fixtures/sprav_orgs_page.html` instead, and note in the spec that `parse_sprav_orgs` takes HTML. Task 3's parser then uses BeautifulSoup like `app/scraper/parser.py`; its contract (`-> list[SpravOrg]`) is unchanged.

- [ ] **Step 4: Save the scrubbed fixture**

Copy the identified response body (the `body` value only, not the wrapper) to `apps/api/tests/fixtures/sprav_orgs_response.json`.

Scrub before saving — this file is committed:
- remove any auth token, CSRF token, cookie, session id, or operator email/phone,
- keep organization names/addresses/ratings (this is business data the operator owns, not a credential),
- trim to at most 3 organizations; the parser contract does not need more.

- [ ] **Step 5: Record findings and clean up**

Add a "Confirmed cabinet payload" section to the design spec with the URL, the JSON path, and the field mapping. Delete the throwaway script and the raw capture:

```bash
rm -rf .local/discover_sprav.py .local/sprav-capture
```

- [ ] **Step 6: Commit**

```bash
git add tests/fixtures/sprav_orgs_response.json ../../docs/superpowers/specs/2026-07-15-sprav-cabinet-scraper-design.md
git commit -m "chore: capture sprav cabinet companies payload fixture"
```

---

### Task 3: `SpravOrg`, `SpravListResult`, and the pure parser

> **Revised after Task 2's discovery.** The original version of this task assumed the cabinet fetches its organization list as an XHR carrying `rating` and `reviews_count`. All three assumptions were wrong. What Task 2 actually found, against the live cabinet:
>
> - The list is **server-rendered** into `window.__PRELOAD_DATA` in the page HTML. There is no companies XHR. (The plan's stated fallback — "if the cabinet server-renders it" — is what happened.)
> - **`rating` and `reviews_count` do not exist.** The string `rating` appears **0 times** in the entire 64 KB preload. These fields are dropped from `SpravOrg`; they are unobtainable here and are still the existing Maps scrapers' job.
> - The records are **chains**, not branches: `type: "chain"`, `total: 2`, with `chain.branchCount` of 357 and 2.
> - `address.formatted` is a **dict** `{"value": "…", "locale": "ru"}`, not a string.
> - `id == permanent_id` — the Yandex Maps permalink. `tycoon_id` is a separate internal id used in cabinet page URLs (`/sprav/chain/{tycoon_id}`).

**Files:**
- Create: `apps/api/app/scraper/yandex_sprav.py`
- Test: `apps/api/tests/test_sprav_parser.py`
- Read: `apps/api/tests/fixtures/sprav_companies_preload.json` (captured and scrubbed in Task 2)

**Interfaces:**
- Consumes: the fixture captured in Task 2.
- Produces:
  - `SpravOrg(sprav_id: str, name: str, address: str | None, url: str | None, org_type: str | None, branch_count: int | None, publishing_status: str | None)`
  - `SpravListResult(organizations: list[SpravOrg], needs_manual_action: bool, error_code: str | None, error_message: str | None, debug_screenshot: str | None, debug_html: str | None)`
  - `extract_preload_data(html: str) -> dict`
  - `parse_sprav_orgs(preload: object) -> list[SpravOrg]`

The parser is split in two so the fixture can be a small scrubbed JSON instead of a 142 KB HTML page carrying the operator's uid, phone, and CSRF token. `extract_preload_data` handles the HTML→dict step; `parse_sprav_orgs` consumes the dict.

- [ ] **Step 1: Write the failing test**

Create `apps/api/tests/test_sprav_parser.py`:

```python
"""Pure parser for the Sprav cabinet companies payload. No I/O, no network.

The cabinet server-renders its company list into window.__PRELOAD_DATA; the
fixture is that structure, scrubbed of everything except business data.
"""

import json
from pathlib import Path

import pytest

from app.scraper.yandex_sprav import SpravOrg, extract_preload_data, parse_sprav_orgs

FIXTURE = Path(__file__).parent / "fixtures" / "sprav_companies_preload.json"


@pytest.fixture
def preload():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_parses_every_organization(preload):
    orgs = parse_sprav_orgs(preload)
    assert len(orgs) == 2
    assert all(isinstance(o, SpravOrg) for o in orgs)


def test_every_organization_has_identity(preload):
    for org in parse_sprav_orgs(preload):
        assert org.sprav_id
        assert org.name


def test_maps_the_chain_fields(preload):
    """The 357-branch chain is the first record; its permalink is the Maps id."""
    org = parse_sprav_orgs(preload)[0]
    assert org.sprav_id == "81562141869"
    assert org.org_type == "chain"
    assert org.branch_count == 357
    assert org.publishing_status == "publish"
    assert org.url == "https://sushi-master.ru/"


def test_address_is_flattened_from_the_formatted_dict(preload):
    """address.formatted is {"value": ..., "locale": ...}, not a string."""
    org = parse_sprav_orgs(preload)[0]
    assert isinstance(org.address, str)


def test_only_the_main_url_is_taken(preload):
    """The record also carries a 'social' url; it must not win."""
    org = parse_sprav_orgs(preload)[0]
    assert "vk.com" not in (org.url or "")


@pytest.mark.parametrize("bad", [
    {},
    [],
    None,
    "",
    "not json at all",
    {"unexpected": "shape"},
    {"initialState": None},
    {"initialState": {"companiesList": None}},
    {"initialState": {"companiesList": {"listCompanies": None}}},
    {"initialState": {"companiesList": {"listCompanies": "nope"}}},
    42,
])
def test_degenerate_payloads_return_empty_without_raising(bad):
    """Safe degradation: a cabinet change must surface as an empty run, never a crash."""
    assert parse_sprav_orgs(bad) == []


def test_record_without_identity_is_skipped():
    payload = {"initialState": {"companiesList": {"listCompanies": [
        {"displayName": "no id here"},
        {"permanent_id": 123},
        {"permanent_id": 456, "displayName": "keeper"},
    ]}}}
    orgs = parse_sprav_orgs(payload)
    assert len(orgs) == 1
    assert orgs[0].sprav_id == "456"


def test_record_missing_optional_fields_still_parses():
    payload = {"initialState": {"companiesList": {"listCompanies": [
        {"permanent_id": 999, "displayName": "Bare"},
    ]}}}
    org = parse_sprav_orgs(payload)[0]
    assert org.address is None
    assert org.url is None
    assert org.branch_count is None
    assert org.publishing_status is None


def test_extract_preload_data_reads_the_inline_script():
    html = '<html><script nonce="">window.__PRELOAD_DATA = {"a": {"b": 1}};</script></html>'
    assert extract_preload_data(html) == {"a": {"b": 1}}


@pytest.mark.parametrize("html", [
    "",
    "<html>nothing here</html>",
    "<html><script>window.__PRELOAD_DATA = not-json;</script></html>",
    "<html><script>window.__OTHER = {\"a\": 1};</script></html>",
])
def test_extract_preload_data_returns_empty_on_anything_unexpected(html):
    assert extract_preload_data(html) == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_sprav_parser.py -v`

Expected: FAIL — `ModuleNotFoundError: No module named 'app.scraper.yandex_sprav'`.

- [ ] **Step 3: Write the module**

Create `apps/api/app/scraper/yandex_sprav.py`:

```python
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
        return int(value)
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_sprav_parser.py -v`

Expected: PASS (all cases).

- [ ] **Step 5: Commit**

```bash
git add app/scraper/yandex_sprav.py tests/test_sprav_parser.py tests/fixtures/sprav_companies_preload.json
git commit -m "feat: pure parser for sprav cabinet organization list"
```

---

### Task 4: `YandexSpravScraper` — Playwright I/O layer

> **Revised after Task 2's discovery.** The original version registered a `page.on("response")` handler to capture a companies XHR. No such XHR exists — the list is inlined in the HTML. The interception code is gone; the scraper now reads `page.content()` and hands it to `extract_preload_data`. Verified live: with a valid storage-state, `https://yandex.ru/sprav/` redirects to `https://yandex.ru/sprav/companies` and renders the list; with no session it redirects to `passport.yandex.ru`.

**Files:**
- Modify: `apps/api/app/scraper/yandex_sprav.py`
- Modify: `apps/api/app/core/config.py` (add settings after the `http_scrape_*` block)
- Test: `apps/api/tests/test_sprav_scraper.py`

**Interfaces:**
- Consumes: `extract_preload_data`, `parse_sprav_orgs`, `SpravListResult` (Task 3); `BOT_MARKERS` from `app.scraper.markers`; `save_debug_artifacts` from `app.scraper.debug_artifacts`; `YandexPublicScraper.LOCALE` / `EXTRA_HTTP_HEADERS`.
- Produces:
  - `YandexSpravScraper.list_organizations(storage_state_path: str) -> SpravListResult`
  - `YandexSpravScraper._is_challenge(html: str, url: str) -> bool` (static, pure — the tested seam)
  - `settings.sprav_companies_url`, `settings.sprav_orgs_output_path`, `settings.sprav_page_timeout_ms`

- [ ] **Step 1: Write the failing test**

Create `apps/api/tests/test_sprav_scraper.py`:

```python
"""Sprav scraper I/O contract: session preconditions and challenge detection.

Playwright itself is not exercised (constitution: no live-network tests); only
the pure seams are.
"""

from app.scraper.yandex_sprav import YandexSpravScraper


def test_missing_storage_state_short_circuits(tmp_path):
    """No session file must not launch a browser."""
    result = YandexSpravScraper().list_organizations(str(tmp_path / "absent.json"))
    assert result.needs_manual_action is True
    assert result.error_code == "missing_session"
    assert result.organizations == []


def test_empty_storage_state_short_circuits(tmp_path):
    state = tmp_path / "empty.json"
    state.write_text("", encoding="utf-8")
    result = YandexSpravScraper().list_organizations(str(state))
    assert result.needs_manual_action is True
    assert result.error_code == "missing_session"


def test_passport_redirect_is_a_challenge():
    """An expired session bounces to Passport — that needs a human, not a retry."""
    assert YandexSpravScraper._is_challenge("<html>ok</html>", "https://passport.yandex.ru/auth") is True


def test_bot_marker_is_a_challenge():
    assert YandexSpravScraper._is_challenge(
        "<html>Обнаружена защита от ботов</html>", "https://yandex.ru/sprav/companies"
    ) is True


def test_rendered_cabinet_page_is_not_a_challenge():
    assert YandexSpravScraper._is_challenge(
        "<html><script>window.__PRELOAD_DATA = {};</script></html>",
        "https://yandex.ru/sprav/companies",
    ) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_sprav_scraper.py -v`

Expected: FAIL — `AttributeError: type object 'YandexSpravScraper' has no attribute '_is_challenge'`.

- [ ] **Step 3: Add the settings**

In `apps/api/app/core/config.py`, after the `http_scrape_*` block (line 29), add:

```python
    # Sprav cabinet reader (feature 011, console-only). Read-only: the cabinet
    # entry point is settings-driven so a URL change is a config edit. The
    # cabinet redirects /sprav/ -> /sprav/companies and inlines the list.
    sprav_companies_url: str = "https://yandex.ru/sprav/"
    sprav_orgs_output_path: str = ".local/sprav-orgs.json"
    sprav_page_timeout_ms: int = 90000
```

- [ ] **Step 4: Write the scraper**

Append to `apps/api/app/scraper/yandex_sprav.py` (move the new imports up to the module's import block):

```python
from pathlib import Path

from playwright.sync_api import sync_playwright

from app.core.config import settings
from app.scraper.debug_artifacts import save_debug_artifacts
from app.scraper.markers import BOT_MARKERS
from app.scraper.yandex_public import YandexPublicScraper


class YandexSpravScraper:
    """Reads the operator's organization list from the Yandex Business cabinet.

    Reuses the operator storage-state: the cabinet and Maps share the .yandex.ru
    Passport cookies, so no separate session is needed.
    """

    @staticmethod
    def _is_challenge(html: str, url: str) -> bool:
        """Passport redirect or a bot wall — both mean a human must intervene."""
        if "passport.yandex" in url:
            return True
        lowered = html.lower()
        return any(marker.lower() in lowered for marker in BOT_MARKERS)

    def list_organizations(self, storage_state_path: str) -> SpravListResult:
        path = Path(storage_state_path)
        if not path.exists() or path.stat().st_size == 0:
            return SpravListResult(
                needs_manual_action=True,
                error_code="missing_session",
                error_message="Storage state not found — run: python -m scripts.sprav_login",
            )

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
                    page.goto(
                        settings.sprav_companies_url,
                        wait_until="networkidle",
                        timeout=settings.sprav_page_timeout_ms,
                    )
                    html = page.content()

                    if self._is_challenge(html, page.url):
                        shot, dbg = save_debug_artifacts(page, "sprav-list")
                        return SpravListResult(
                            needs_manual_action=True,
                            error_code="access_challenge",
                            error_message="Session invalid or captcha — run: python -m scripts.sprav_login",
                            debug_screenshot=shot,
                            debug_html=dbg,
                        )

                    orgs = parse_sprav_orgs(extract_preload_data(html))
                    if not orgs:
                        shot, dbg = save_debug_artifacts(page, "sprav-list-empty")
                        return SpravListResult(
                            error_code="sprav_list_not_found",
                            error_message="Cabinet page carried no organization list",
                            debug_screenshot=shot,
                            debug_html=dbg,
                        )
                    return SpravListResult(organizations=orgs)
                finally:
                    browser.close()
        except Exception as exc:
            return SpravListResult(error_code="sprav_scrape_error", error_message=str(exc))
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_sprav_scraper.py tests/test_sprav_parser.py -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add app/scraper/yandex_sprav.py app/core/config.py tests/test_sprav_scraper.py
git commit -m "feat: sprav cabinet scraper I/O layer with challenge detection"
```

---


### Task 5: `sprav_orgs` command

**Files:**
- Create: `apps/api/scripts/sprav_orgs.py`
- Test: `apps/api/tests/test_sprav_orgs_cli.py`

**Interfaces:**
- Consumes: `YandexSpravScraper.list_organizations`, `SpravListResult`, `SpravOrg` (Tasks 3-4); `settings.sprav_orgs_output_path`.
- Produces: `scripts.sprav_orgs.orgs_to_json(orgs: list[SpravOrg], pretty: bool) -> str`, `scripts.sprav_orgs.exit_code_for(result: SpravListResult) -> int`.

- [ ] **Step 1: Write the failing test**

Create `apps/api/tests/test_sprav_orgs_cli.py`:

```python
"""Sprav org-list CLI: serialization and exit-code contract."""

import json

from app.scraper.yandex_sprav import SpravListResult, SpravOrg
from scripts.sprav_orgs import exit_code_for, orgs_to_json


def _org():
    return SpravOrg(
        sprav_id="81562141869",
        name="Суши Мастер",
        address="Земля",
        url="https://sushi-master.ru/",
        org_type="chain",
        branch_count=357,
        publishing_status="publish",
    )


def test_orgs_to_json_roundtrips_all_fields():
    payload = json.loads(orgs_to_json([_org()], pretty=False))
    assert payload == [{
        "sprav_id": "81562141869",
        "name": "Суши Мастер",
        "address": "Земля",
        "url": "https://sushi-master.ru/",
        "org_type": "chain",
        "branch_count": 357,
        "publishing_status": "publish",
    }]


def test_orgs_to_json_keeps_cyrillic_readable():
    assert "Суши Мастер" in orgs_to_json([_org()], pretty=False)


def test_orgs_to_json_pretty_is_indented():
    assert "\n  " in orgs_to_json([_org()], pretty=True)


def test_empty_list_serializes_to_empty_array():
    assert json.loads(orgs_to_json([], pretty=False)) == []


def test_exit_code_success():
    assert exit_code_for(SpravListResult(organizations=[_org()])) == 0


def test_exit_code_needs_manual_action():
    assert exit_code_for(SpravListResult(needs_manual_action=True, error_code="access_challenge")) == 2


def test_exit_code_error():
    assert exit_code_for(SpravListResult(error_code="sprav_scrape_error")) == 1


def test_exit_code_empty_result_is_not_success():
    """No orgs and no error still means the run told us nothing — do not exit 0."""
    assert exit_code_for(SpravListResult()) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_sprav_orgs_cli.py -v`

Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.sprav_orgs'`.

- [ ] **Step 3: Write the CLI**

Create `apps/api/scripts/sprav_orgs.py`:

```python
"""Read the operator's organization list from the Yandex Business cabinet.

Read-only. Prints the organizations as JSON on stdout (pipeable to jq) and
writes the same JSON to a file. Diagnostics go to stderr.

  python -m scripts.sprav_orgs
  python -m scripts.sprav_orgs --pretty --out .local/sprav-orgs.json

Exit codes: 0 organizations found, 2 needs_manual_action, 1 error/empty.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from pathlib import Path

from app.core.config import settings
from app.scraper.yandex_sprav import SpravListResult, SpravOrg, YandexSpravScraper

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_MANUAL = 2


def orgs_to_json(orgs: list[SpravOrg], pretty: bool) -> str:
    payload = [dataclasses.asdict(org) for org in orgs]
    # ensure_ascii=False so Cyrillic names stay readable in the file and terminal.
    return json.dumps(payload, ensure_ascii=False, indent=2 if pretty else None)


def exit_code_for(result: SpravListResult) -> int:
    if result.needs_manual_action:
        return EXIT_MANUAL
    if result.error_code or not result.organizations:
        return EXIT_ERROR
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read the Sprav cabinet organization list.")
    parser.add_argument("--out", default=settings.sprav_orgs_output_path, help="Where to write the JSON.")
    parser.add_argument("--pretty", action="store_true", help="Indent the JSON.")
    args = parser.parse_args(argv)

    result = YandexSpravScraper().list_organizations(settings.yandex_storage_state_path)

    if result.needs_manual_action or result.error_code:
        print(f"error:   {result.error_code}", file=sys.stderr)
        print(f"message: {result.error_message}", file=sys.stderr)
        if result.debug_html:
            print(f"debug:   {result.debug_html}", file=sys.stderr)
        return exit_code_for(result)

    document = orgs_to_json(result.organizations, pretty=args.pretty)
    print(document)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(document, encoding="utf-8")
    print(f"wrote {len(result.organizations)} organizations to {out}", file=sys.stderr)

    return exit_code_for(result)


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_sprav_orgs_cli.py -v`

Expected: PASS (8 passed).

- [ ] **Step 5: Run the whole suite for regressions**

Run: `pytest -v`

Expected: PASS — no existing test broken. The only pre-existing file touched is `yandex_auth.py` (new defaulted parameter) and `config.py` (new defaulted settings).

- [ ] **Step 6: Commit**

```bash
git add scripts/sprav_orgs.py tests/test_sprav_orgs_cli.py
git commit -m "feat: sprav_orgs command emitting the cabinet organization list as JSON"
```

---

### Task 6: End-to-end verification against the live cabinet

Automated tests cover only the pure seams; this task proves the two commands actually work together against the real cabinet.

**Files:** none (verification only)

**Interfaces:**
- Consumes: everything from Tasks 1-5.

- [ ] **Step 1: Verify the session**

Run: `python -m scripts.sprav_login --check`

Expected: `status: valid`, exit code 0. If not, run `python -m scripts.sprav_login` and sign in by hand.

- [ ] **Step 2: Read the organization list**

Run: `python -m scripts.sprav_orgs --pretty`

Expected: a JSON array of organizations on stdout; `wrote N organizations to .local/sprav-orgs.json` on stderr; exit code 0.

- [ ] **Step 3: Confirm the count is plausible**

Compare `N` against the number of organizations the operator actually manages in the cabinet UI. A mismatch means the cabinet paginates the list — record it as a follow-up; do not silently accept a truncated list.

- [ ] **Step 4: Confirm no secrets leaked**

Run: `grep -riE "session_id|sessionid2|passwd|password|cookie" .local/sprav-orgs.json`

Expected: no matches.

- [ ] **Step 5: Confirm the output file is gitignored**

Run: `git status --short && git check-ignore -v .local/sprav-orgs.json`

Expected: `.local/sprav-orgs.json` is ignored via the `.local/` rule and absent from `git status`.

---

## Follow-ups (not in this plan)

- Cabinet pagination, if Task 6 Step 3 reveals a truncated list.
- Reading reviews from the cabinet (the original motivation; needs its own spec).
- Persisting cabinet organizations to the `organizations` table / mapping to existing rows.
- A `ScrapeMode`, API endpoint, or web page for the cabinet.
