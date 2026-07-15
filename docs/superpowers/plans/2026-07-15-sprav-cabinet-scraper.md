# Yandex Sprav Cabinet Scraper Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Read the list of organizations the operator manages from the Yandex Business cabinet (`https://yandex.ru/sprav/`), driven from two console commands, using the storage-state session the project already produces.

**Architecture:** A Playwright context loaded with the existing operator storage-state opens the cabinet and captures the companies-list XHR. I/O lives in `YandexSpravScraper`; parsing lives in a pure `parse_sprav_orgs` function that is the only unit-tested piece. Two operator CLIs (`sprav_login`, `sprav_orgs`) drive it. Nothing is written to the database.

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
| `apps/api/app/scraper/yandex_auth.py` (modify) | Add `headless` parameter to `login`. Existing behaviour is the default. |
| `apps/api/app/scraper/yandex_sprav.py` (create) | `SpravOrg`, `SpravListResult`, pure `parse_sprav_orgs`, and the `YandexSpravScraper` Playwright I/O class. |
| `apps/api/app/core/config.py` (modify) | `sprav_companies_url`, `sprav_orgs_output_path`. |
| `apps/api/scripts/sprav_login.py` (create) | Auth test command. |
| `apps/api/scripts/sprav_orgs.py` (create) | Org-list command: JSON to stdout + file. |
| `apps/api/tests/test_sprav_login_cli.py` (create) | Exit-code mapping + no-credentials short circuit. |
| `apps/api/tests/test_sprav_parser.py` (create) | `parse_sprav_orgs` happy path + degenerate inputs. |
| `apps/api/tests/test_sprav_scraper.py` (create) | Missing-session short circuit + challenge detection. |
| `apps/api/tests/fixtures/sprav_orgs_response.json` (create, Task 2) | Real captured cabinet payload, credential-scrubbed. |

Parser and scraper share one module because they change together (a payload shape change touches both) and the module stays small. This mirrors `yandex_http.py`, which delegates to a parser but keeps its own transport concerns local.

---

### Task 1: `headless` parameter + `sprav_login` command

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

### Task 2: Discovery spike — capture the real cabinet payload

**This is an exploratory task, not a TDD task.** Its deliverable is knowledge plus a fixture. Tasks 3-5 depend on it; do not guess the payload shape ahead of it.

**Files:**
- Create: `apps/api/tests/fixtures/sprav_orgs_response.json`
- Modify: `docs/superpowers/specs/2026-07-15-sprav-cabinet-scraper-design.md` (record the confirmed endpoint + shape)

**Interfaces:**
- Consumes: `python -m scripts.sprav_login` from Task 1 (a valid session must exist first).
- Produces: the fixture file, and the confirmed answers to: (a) the companies-list request URL, (b) whether the list is XHR-fetched or server-rendered, (c) the JSON path to the organization array, (d) the field names for id/name/address/rating/reviews count.

- [ ] **Step 1: Establish a session**

Run: `python -m scripts.sprav_login` (or `--headed` if it reports `needs_manual_action`).

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

**If `page.url` redirected to `passport.yandex.ru`:** the session is not valid for the cabinet — stop and re-run Task 2 Step 1 with `--headed`. Do not proceed on a guess.

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

**Files:**
- Create: `apps/api/app/scraper/yandex_sprav.py`
- Test: `apps/api/tests/test_sprav_parser.py`
- Read: `apps/api/tests/fixtures/sprav_orgs_response.json` (from Task 2)

**Interfaces:**
- Consumes: the fixture and field mapping confirmed in Task 2.
- Produces:
  - `SpravOrg(sprav_id: str, name: str, address: str | None, rating: float | None, reviews_count: int | None, url: str | None)`
  - `SpravListResult(organizations: list[SpravOrg], needs_manual_action: bool, error_code: str | None, error_message: str | None, debug_screenshot: str | None, debug_html: str | None)`
  - `parse_sprav_orgs(payload: object) -> list[SpravOrg]`

- [ ] **Step 1: Write the failing test**

Create `apps/api/tests/test_sprav_parser.py`. The degenerate cases are exact; the happy-path assertions read the real values out of the Task 2 fixture rather than hardcoding invented ones.

```python
"""Pure parser for the Sprav cabinet companies payload. No I/O, no network."""

import json
from pathlib import Path

import pytest

from app.scraper.yandex_sprav import SpravOrg, parse_sprav_orgs

FIXTURE = Path(__file__).parent / "fixtures" / "sprav_orgs_response.json"


@pytest.fixture
def payload():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_parses_every_organization(payload):
    orgs = parse_sprav_orgs(payload)
    assert len(orgs) > 0
    assert all(isinstance(o, SpravOrg) for o in orgs)


def test_every_organization_has_identity(payload):
    """id and name are the two fields the cabinet always provides; without
    them a record is useless downstream."""
    for org in parse_sprav_orgs(payload):
        assert org.sprav_id
        assert org.name


def test_optional_fields_are_correctly_typed(payload):
    for org in parse_sprav_orgs(payload):
        assert org.rating is None or isinstance(org.rating, float)
        assert org.reviews_count is None or isinstance(org.reviews_count, int)
        assert org.address is None or isinstance(org.address, str)
        assert org.url is None or isinstance(org.url, str)


@pytest.mark.parametrize("bad", [
    {},
    [],
    None,
    "",
    "not json at all",
    {"unexpected": "shape"},
    {"result": None},
    {"result": {"companies": None}},
    42,
])
def test_degenerate_payloads_return_empty_without_raising(bad):
    """Analysis-style safe degradation: never raise on unexpected input."""
    assert parse_sprav_orgs(bad) == []


def test_record_missing_optional_fields_still_parses():
    """A record with only identity fields must survive with None optionals.

    Uses the identity field names confirmed in Task 2 — substitute them here.
    """
    orgs = parse_sprav_orgs(_minimal_payload())
    assert len(orgs) == 1
    assert orgs[0].rating is None
    assert orgs[0].reviews_count is None
    assert orgs[0].address is None
```

Add `_minimal_payload()` to the test file, built from the shape confirmed in Task 2 — the smallest payload carrying exactly one record with only id and name populated.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_sprav_parser.py -v`

Expected: FAIL — `ModuleNotFoundError: No module named 'app.scraper.yandex_sprav'`.

- [ ] **Step 3: Write the module**

Create `apps/api/app/scraper/yandex_sprav.py`. Fill `_ORG_ARRAY_PATH` and the field names from Task 2's findings.

```python
"""Yandex Sprav (Business cabinet) reader — organization list.

Read-only: the cabinet also exposes editing and review replies; this module
performs GET/read only (constitution hard rule). Parsing is pure and lives
beside the Playwright I/O, mirroring the yandex_http.py / parser.py split.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SpravOrg:
    sprav_id: str
    name: str
    address: str | None = None
    rating: float | None = None
    reviews_count: int | None = None
    url: str | None = None


@dataclass
class SpravListResult:
    organizations: list[SpravOrg] = field(default_factory=list)
    needs_manual_action: bool = False
    error_code: str | None = None
    error_message: str | None = None
    debug_screenshot: str | None = None
    debug_html: str | None = None


def _as_float(value: object) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.replace(",", ".").strip())
        except ValueError:
            return None
    return None


def _as_int(value: object) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        digits = "".join(ch for ch in value if ch.isdigit())
        return int(digits) if digits else None
    return None


def _as_str(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _dig(payload: object, path: tuple[str, ...]) -> object:
    """Walk a dotted path, returning None the moment the shape disagrees."""
    current = payload
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


# JSON path to the organization array — confirmed in Task 2.
_ORG_ARRAY_PATH: tuple[str, ...] = ()


def _parse_one(raw: object) -> SpravOrg | None:
    if not isinstance(raw, dict):
        return None
    # Field names confirmed in Task 2.
    sprav_id = _as_str(raw.get("id"))
    name = _as_str(raw.get("name"))
    if not sprav_id or not name:
        return None
    return SpravOrg(
        sprav_id=sprav_id,
        name=name,
        address=_as_str(raw.get("address")),
        rating=_as_float(raw.get("rating")),
        reviews_count=_as_int(raw.get("reviews_count")),
        url=_as_str(raw.get("url")),
    )


def parse_sprav_orgs(payload: object) -> list[SpravOrg]:
    """Map the cabinet companies payload to SpravOrg records.

    Degrades safely: any unexpected shape yields [] rather than raising, so a
    cabinet change surfaces as an empty run, never a crash.
    """
    raw_list = _dig(payload, _ORG_ARRAY_PATH) if _ORG_ARRAY_PATH else payload
    if not isinstance(raw_list, list):
        return []
    parsed = (_parse_one(item) for item in raw_list)
    return [org for org in parsed if org is not None]
```

Adjust `_ORG_ARRAY_PATH` and the `raw.get(...)` keys in `_parse_one` to the names confirmed in Task 2. If Task 2 found the list is server-rendered, replace `_dig`/`parse_sprav_orgs` internals with a BeautifulSoup parse of the HTML (`from bs4 import BeautifulSoup`, as in `app/scraper/parser.py`) — the signature and return type stay identical.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_sprav_parser.py -v`

Expected: PASS (all cases).

- [ ] **Step 5: Commit**

```bash
git add app/scraper/yandex_sprav.py tests/test_sprav_parser.py
git commit -m "feat: pure parser for sprav cabinet organization list"
```

---

### Task 4: `YandexSpravScraper` — Playwright I/O layer

**Files:**
- Modify: `apps/api/app/scraper/yandex_sprav.py`
- Modify: `apps/api/app/core/config.py:22` (add settings next to the other scraper blocks)
- Test: `apps/api/tests/test_sprav_scraper.py`

**Interfaces:**
- Consumes: `parse_sprav_orgs`, `SpravListResult` (Task 3); `BOT_MARKERS` from `app.scraper.markers`; `save_debug_artifacts` from `app.scraper.debug_artifacts`; `YandexPublicScraper.LOCALE` / `EXTRA_HTTP_HEADERS`.
- Produces:
  - `YandexSpravScraper.list_organizations(storage_state_path: str) -> SpravListResult`
  - `YandexSpravScraper._is_challenge(html: str, url: str) -> bool` (static, pure — the tested seam)
  - `settings.sprav_companies_url`, `settings.sprav_orgs_output_path`

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
    assert YandexSpravScraper._is_challenge("<html>ok</html>", "https://passport.yandex.ru/auth") is True


def test_bot_marker_is_a_challenge():
    assert YandexSpravScraper._is_challenge(
        "<html>Обнаружена защита от ботов</html>", "https://yandex.ru/sprav/"
    ) is True


def test_normal_cabinet_page_is_not_a_challenge():
    assert YandexSpravScraper._is_challenge(
        "<html><div>Мои организации</div></html>", "https://yandex.ru/sprav/"
    ) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_sprav_scraper.py -v`

Expected: FAIL — `AttributeError: type object 'YandexSpravScraper' has no attribute '_is_challenge'`.

- [ ] **Step 3: Add the settings**

In `apps/api/app/core/config.py`, after the `http_scrape_*` block (line 29), add:

```python
    # Sprav cabinet reader (feature 011, console-only). Read-only: the cabinet
    # entry point is settings-driven so a URL change is a config edit.
    sprav_companies_url: str = "https://yandex.ru/sprav/"
    sprav_orgs_output_path: str = ".local/sprav-orgs.json"
    sprav_page_timeout_ms: int = 60000
```

- [ ] **Step 4: Write the scraper**

Append to `apps/api/app/scraper/yandex_sprav.py`:

```python
from pathlib import Path

from playwright.sync_api import sync_playwright

from app.core.config import settings
from app.scraper.debug_artifacts import save_debug_artifacts
from app.scraper.markers import BOT_MARKERS
from app.scraper.yandex_public import YandexPublicScraper


class YandexSpravScraper:
    """Reads the operator's organization list from the Yandex Business cabinet.

    Reuses the operator storage-state: cabinet and Maps share the .yandex.ru
    Passport cookies, so no separate session is needed.
    """

    def _capture_companies_json(self, page) -> list[object]:
        """Collect JSON bodies that look like the companies list.

        Registered before navigation so the initial fetch is not missed.
        """
        captured: list[object] = []

        def on_response(response) -> None:
            if "json" not in response.headers.get("content-type", ""):
                return
            try:
                captured.append(response.json())
            except Exception:
                return

        page.on("response", on_response)
        return captured

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
                    captured = self._capture_companies_json(page)
                    page.goto(
                        settings.sprav_companies_url,
                        wait_until="networkidle",
                        timeout=settings.sprav_page_timeout_ms,
                    )

                    if self._is_challenge(page.content(), page.url):
                        shot, html = save_debug_artifacts(page, "sprav-list")
                        return SpravListResult(
                            needs_manual_action=True,
                            error_code="access_challenge",
                            error_message="Session invalid or captcha — run: python -m scripts.sprav_login --headed",
                            debug_screenshot=shot,
                            debug_html=html,
                        )

                    for payload in captured:
                        orgs = parse_sprav_orgs(payload)
                        if orgs:
                            return SpravListResult(organizations=orgs)

                    shot, html = save_debug_artifacts(page, "sprav-list-not-found")
                    return SpravListResult(
                        error_code="sprav_list_not_found",
                        error_message="No response matched the companies payload",
                        debug_screenshot=shot,
                        debug_html=html,
                    )
                finally:
                    browser.close()
        except Exception as exc:
            return SpravListResult(error_code="sprav_scrape_error", error_message=str(exc))
```

Move the `from pathlib import Path` / Playwright / settings imports to the top of the module with the existing imports rather than leaving them mid-file.

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
        sprav_id="123",
        name="Суши Мастер",
        address="Сочи, ул. Ленина, 1",
        rating=4.7,
        reviews_count=42,
        url="https://yandex.ru/maps/org/x/123/",
    )


def test_orgs_to_json_roundtrips_all_fields():
    payload = json.loads(orgs_to_json([_org()], pretty=False))
    assert payload == [{
        "sprav_id": "123",
        "name": "Суши Мастер",
        "address": "Сочи, ул. Ленина, 1",
        "rating": 4.7,
        "reviews_count": 42,
        "url": "https://yandex.ru/maps/org/x/123/",
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

Expected: `status: valid`, exit code 0. If not, run `python -m scripts.sprav_login` (add `--headed` on `needs_manual_action`).

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
