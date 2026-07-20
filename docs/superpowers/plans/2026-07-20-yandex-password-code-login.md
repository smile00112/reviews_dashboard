# Yandex password + confirmation-code login Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the `/settings` "Yandex connection" card drive a real automated login (password → push/SMS confirmation code) that saves a working `operator_auth` session, replacing the currently-dead `YandexAuthScraper.login()` path.

**Architecture:** A new `SessionStatus.awaiting_code` + `ScraperSession.pending_code` column let the existing background-task/poll pattern (feature 010) pause mid-login for a code the operator submits through a new `POST /session/code` endpoint. `YandexAuthScraper.login_with_password` drives headless Playwright through Passport using resilient text/role locators (not the old, broken `name=`/`id` selectors) and blocks on an injected `request_code()` callback owned by `ScrapeService`, which does all the DB polling — the scraper layer never touches the database.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, Playwright (sync API), pytest, Next.js App Router (client components), existing `lib/api.ts` `request<T>` wrapper.

## Global Constraints

- Credentials (`YANDEX_OPERATOR_LOGIN`/`YANDEX_OPERATOR_PASSWORD`) stay in env only — never collected or displayed by the web UI; only the one-time confirmation code is ever accepted from the browser.
- No captcha/bot-wall bypass — any bot-wall/captcha marker at any step ends the attempt as `needs_manual_action`, never a silent retry.
- Read-only — this feature only authenticates, no writes to Yandex properties.
- `app/scraper/*` must stay DB-free — the code-wait/polling logic lives in `ScrapeService`, injected into the scraper as a plain callback.
- `pending_code` is never logged and never included in any API response body.
- Confirmation code input from the browser is validated (digits only, bounded length) before it ever reaches a Playwright `fill()` call.

---

## File Structure

- `apps/api/app/models/enums.py` — add `SessionStatus.awaiting_code` (modify).
- `apps/api/app/models/scraper_session.py` — add `pending_code` column (modify).
- `apps/api/alembic/versions/0019_session_awaiting_code.py` — new migration.
- `apps/api/app/core/config.py` — add two settings (modify).
- `apps/api/app/services/scrape_service.py` — `_request_code`, `submit_code`, `login_operator` wiring (modify).
- `apps/api/app/scraper/yandex_auth.py` — `login_with_password`, `_passport_challenge`, `_fill_code`, module-level `_looks_like_code_screen` (modify).
- `apps/api/app/schemas/scraper_session.py` — `CodeSubmission` schema (modify).
- `apps/api/app/api/scraper_sessions.py` — `POST /session/code` route (modify).
- `apps/api/tests/test_scraper_session_awaiting_code_model.py` — new, Task 1.
- `apps/api/tests/test_scraper_session_async.py` — stub update, Task 3 (modify).
- `apps/api/tests/test_request_code_polling.py` — new, Task 3.
- `apps/api/tests/test_yandex_auth_scraper.py` — add `_looks_like_code_screen` tests, Task 4 (modify).
- `apps/api/tests/test_yandex_code_login.py` — new, Task 5 (API contract).
- `apps/api/tests/test_scrape_endpoints_require_admin.py` — add auth-gating tests, Task 5 (modify).
- `apps/web/lib/types.ts` — extend `SessionStatus` union, Task 6 (modify).
- `apps/web/lib/api.ts` — `submitSessionCode`, Task 6 (modify).
- `apps/web/components/settings/yandex-connection.tsx` — new, Task 7.
- `apps/web/app/(dashboard)/settings/page.tsx` — mount the new card, Task 7 (modify).

---

### Task 1: Data model — `awaiting_code` status + `pending_code` column

**Files:**
- Modify: `apps/api/app/models/enums.py`
- Modify: `apps/api/app/models/scraper_session.py`
- Create: `apps/api/alembic/versions/0019_session_awaiting_code.py`
- Test: `apps/api/tests/test_scraper_session_awaiting_code_model.py`

**Interfaces:**
- Produces: `SessionStatus.awaiting_code` (enum member), `ScraperSession.pending_code: str | None` (SQLAlchemy mapped column, nullable, default `None`).

- [ ] **Step 1: Write the failing test**

```python
# apps/api/tests/test_scraper_session_awaiting_code_model.py
"""ScraperSession gains an awaiting_code status + pending_code column
(Yandex password+confirmation-code login feature)."""

from app.models.enums import SessionStatus
from app.models.scraper_session import ScraperSession


def test_scraper_session_defaults_pending_code_to_none(db_session):
    session = ScraperSession(provider="yandex", storage_state_path="/tmp/state.json")
    db_session.add(session)
    db_session.commit()
    db_session.refresh(session)

    assert session.pending_code is None


def test_scraper_session_can_be_set_to_awaiting_code_with_a_pending_code(db_session):
    session = ScraperSession(provider="yandex", storage_state_path="/tmp/state.json")
    db_session.add(session)
    db_session.commit()

    session.status = SessionStatus.awaiting_code
    session.pending_code = "123456"
    db_session.commit()
    db_session.refresh(session)

    assert session.status == SessionStatus.awaiting_code
    assert session.pending_code == "123456"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/api && pytest tests/test_scraper_session_awaiting_code_model.py -v`
Expected: FAIL — `AttributeError: 'ScraperSession' object has no attribute 'pending_code'` (or `AttributeError: awaiting_code` on the enum).

- [ ] **Step 3: Add the enum member**

In `apps/api/app/models/enums.py`, extend `SessionStatus`:

```python
class SessionStatus(str, enum.Enum):
    missing = "missing"
    valid = "valid"
    expired = "expired"
    needs_manual_action = "needs_manual_action"
    # Background login/check scheduled but not finished (feature 010).
    pending = "pending"
    # Playwright is paused mid-login waiting for the operator to submit the
    # push/SMS confirmation code (Yandex password+confirmation-code login).
    awaiting_code = "awaiting_code"
```

- [ ] **Step 4: Add the column**

In `apps/api/app/models/scraper_session.py`, add `pending_code` next to `status`:

```python
from sqlalchemy import DateTime, Enum, Text, func
```

(import unchanged — `Text` already imported). Add the column:

```python
    status: Mapped[SessionStatus] = mapped_column(
        Enum(SessionStatus, name="session_status_enum", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=SessionStatus.missing,
    )
    # One-time confirmation code the operator submits via POST /session/code
    # while status == awaiting_code; consumed (cleared to None) the instant
    # the background login picks it up. Never returned by any API response.
    pending_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd apps/api && pytest tests/test_scraper_session_awaiting_code_model.py -v`
Expected: PASS (tests run against the SQLite test DB, so no migration is needed for them to pass).

- [ ] **Step 6: Write the migration**

```python
# apps/api/alembic/versions/0019_session_awaiting_code.py
"""session_status 'awaiting_code' value + scraper_sessions.pending_code
(Yandex password+confirmation-code login).

Additive only. ``ALTER TYPE ... ADD VALUE`` is irreversible on PostgreSQL —
the downgrade drops the column but leaves the enum value in place (harmless).

Revision ID: 0019_session_awaiting_code
Revises: 0018_app_settings
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# NB: alembic_version.version_num is varchar(32) — keep this id short.
revision: str = "0019_session_awaiting_code"
down_revision: Union[str, None] = "0018_app_settings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        with op.get_context().autocommit_block():
            op.execute("ALTER TYPE session_status_enum ADD VALUE IF NOT EXISTS 'awaiting_code'")
    op.add_column("scraper_sessions", sa.Column("pending_code", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("scraper_sessions", "pending_code")
    # session_status_enum 'awaiting_code' intentionally not removed (see docstring).
```

- [ ] **Step 7: Apply the migration against the local dev DB**

Run: `cd apps/api && alembic upgrade head`
Expected: `Running upgrade 0018_app_settings -> 0019_session_awaiting_code, session_status 'awaiting_code' value + scraper_sessions.pending_code ...`

- [ ] **Step 8: Commit**

```bash
git add apps/api/app/models/enums.py apps/api/app/models/scraper_session.py apps/api/alembic/versions/0019_session_awaiting_code.py apps/api/tests/test_scraper_session_awaiting_code_model.py
git commit -m "feat(scraper-session): add awaiting_code status and pending_code column"
```

---

### Task 2: `ScrapeService` — code-wait polling and `submit_code`

**Files:**
- Modify: `apps/api/app/core/config.py`
- Modify: `apps/api/app/services/scrape_service.py`
- Modify: `apps/api/tests/test_scraper_session_async.py`
- Test: `apps/api/tests/test_request_code_polling.py`

**Interfaces:**
- Consumes: `SessionStatus.awaiting_code`, `ScraperSession.pending_code` (Task 1).
- Produces: `ScrapeService._request_code() -> str | None`, `ScrapeService.submit_code(code: str) -> ScraperSession` (raises `ValueError` if not currently `awaiting_code`). `settings.yandex_code_wait_timeout_seconds: float`, `settings.yandex_code_poll_interval_seconds: float`.

- [ ] **Step 1: Write the failing tests**

```python
# apps/api/tests/test_request_code_polling.py
"""ScrapeService._request_code / submit_code: the DB-polling handoff between
the background login and the operator submitting a confirmation code
(Yandex password+confirmation-code login)."""

import pytest

from app.models.enums import SessionStatus
from app.services import scrape_service as module
from app.services.scrape_service import ScrapeService


def test_request_code_sets_awaiting_code_and_clears_any_stale_code(db_session):
    service = ScrapeService(db_session)
    session = service.get_session_record()
    session.pending_code = "stale"
    db_session.commit()

    # Force an immediate timeout so the test doesn't actually wait.
    from app.core.config import settings as app_settings

    original_timeout = app_settings.yandex_code_wait_timeout_seconds
    app_settings.yandex_code_wait_timeout_seconds = 0
    try:
        code = service._request_code()
    finally:
        app_settings.yandex_code_wait_timeout_seconds = original_timeout

    assert code is None
    session2 = service.get_session_record()
    assert session2.status == SessionStatus.awaiting_code
    assert session2.pending_code is None


def test_request_code_returns_code_once_submitted_mid_wait(db_session, monkeypatch):
    service = ScrapeService(db_session)
    calls = {"n": 0}

    def fake_sleep(seconds):
        calls["n"] += 1
        if calls["n"] == 1:
            # Simulate the operator's POST /session/code landing mid-wait.
            fresh = service.get_session_record()
            fresh.pending_code = "123456"
            db_session.commit()

    monkeypatch.setattr(module.time, "sleep", fake_sleep)

    code = service._request_code()

    assert code == "123456"
    assert calls["n"] == 1
    session = service.get_session_record()
    assert session.status == SessionStatus.awaiting_code
    assert session.pending_code is None


def test_request_code_times_out_returns_none(db_session, monkeypatch):
    from app.core.config import settings as app_settings

    monkeypatch.setattr(app_settings, "yandex_code_wait_timeout_seconds", 0.02)
    monkeypatch.setattr(app_settings, "yandex_code_poll_interval_seconds", 0.005)

    service = ScrapeService(db_session)
    code = service._request_code()

    assert code is None
    session = service.get_session_record()
    assert session.status == SessionStatus.awaiting_code
    assert session.pending_code is None


def test_submit_code_writes_pending_code_when_awaiting(db_session):
    service = ScrapeService(db_session)
    session = service.get_session_record()
    session.status = SessionStatus.awaiting_code
    db_session.commit()

    result = service.submit_code("654321")

    assert result.pending_code == "654321"
    session2 = service.get_session_record()
    assert session2.pending_code == "654321"


def test_submit_code_rejects_when_not_awaiting(db_session):
    service = ScrapeService(db_session)

    with pytest.raises(ValueError):
        service.submit_code("111111")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd apps/api && pytest tests/test_request_code_polling.py -v`
Expected: FAIL — `AttributeError: 'ScrapeService' object has no attribute '_request_code'`.

- [ ] **Step 3: Add settings**

In `apps/api/app/core/config.py`, add near the other Sprav settings:

```python
    # Yandex password+confirmation-code login: how long the background login
    # waits for the operator to submit the push/SMS code via POST
    # /api/scraper/yandex/session/code before giving up as needs_manual_action.
    yandex_code_wait_timeout_seconds: float = 300.0
    yandex_code_poll_interval_seconds: float = 2.0
```

- [ ] **Step 4: Implement `_request_code` and `submit_code`**

In `apps/api/app/services/scrape_service.py`, add `import time` at the top (alongside the existing `import logging`), then add the two methods near `mark_session_pending`:

```python
    def _request_code(self) -> str | None:
        """Pause the login for the operator's confirmation code. Marks the
        session awaiting_code, then polls pending_code — written by
        submit_code() from a concurrent request — until it appears or the
        configured timeout elapses. DB-only; the scraper layer never touches
        the database (it just calls this as a plain callback)."""
        session = self._get_or_create_session_record()
        session.status = SessionStatus.awaiting_code
        session.pending_code = None
        self.db.commit()

        deadline = time.monotonic() + settings.yandex_code_wait_timeout_seconds
        while time.monotonic() < deadline:
            self.db.refresh(session)
            if session.pending_code:
                code = session.pending_code
                session.pending_code = None
                self.db.commit()
                return code
            time.sleep(settings.yandex_code_poll_interval_seconds)
        return None

    def submit_code(self, code: str) -> ScraperSession:
        session = self._get_or_create_session_record()
        if session.status != SessionStatus.awaiting_code:
            raise ValueError("Session is not awaiting a confirmation code")
        session.pending_code = code
        self.db.commit()
        return session
```

- [ ] **Step 5: Wire `login_operator` to the new scraper method**

In `apps/api/app/services/scrape_service.py`, change `login_operator`:

```python
    def login_operator(self) -> tuple[SessionStatus, str]:
        session = self._get_or_create_session_record()
        try:
            status, message = self.auth_scraper.login_with_password(
                settings.yandex_operator_login,
                settings.yandex_operator_password,
                session.storage_state_path,
                request_code=self._request_code,
            )
        except Exception as exc:  # pending must always reach a terminal state
            logger.exception("operator login failed")
            status, message = SessionStatus.needs_manual_action, f"Login failed: {exc}"
        session.status = status
        if status == SessionStatus.valid:
            session.last_login_at = datetime.now(timezone.utc)
        session.last_checked_at = datetime.now(timezone.utc)
        self.db.commit()
        return status, message
```

- [ ] **Step 6: Update the existing stub in `test_scraper_session_async.py`**

`login_operator` now calls `login_with_password`, not `login` — the fake auth scrapers in this file must match or `test_login_returns_pending_immediately_then_terminal` etc. break:

```python
class _StubAuth:
    def login_with_password(self, login, password, path, request_code=None):
        return SessionStatus.valid, "ok"

    def check_session(self, path):
        return SessionStatus.valid
```

And the `_BoomAuth` class inside `test_login_exception_reaches_terminal_state`:

```python
    class _BoomAuth:
        def login_with_password(self, *a, **kw):
            raise RuntimeError("browser died")
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `cd apps/api && pytest tests/test_request_code_polling.py tests/test_scraper_session_async.py -v`
Expected: all PASS.

- [ ] **Step 8: Commit**

```bash
git add apps/api/app/core/config.py apps/api/app/services/scrape_service.py apps/api/tests/test_request_code_polling.py apps/api/tests/test_scraper_session_async.py
git commit -m "feat(scraper-session): poll for the operator's confirmation code during login"
```

---

### Task 3: `YandexAuthScraper.login_with_password`

**Files:**
- Modify: `apps/api/app/scraper/yandex_auth.py`
- Modify: `apps/api/tests/test_yandex_auth_scraper.py`

**Interfaces:**
- Consumes: `request_code: Callable[[], str | None] | None` (Task 2's `ScrapeService._request_code`, passed positionally-by-keyword — the scraper only needs the callable shape, no import of `ScrapeService`).
- Produces: `YandexAuthScraper.login_with_password(login, password, storage_state_path, request_code=None) -> tuple[SessionStatus, str]`, module-level `_looks_like_code_screen(html: str) -> bool`.

- [ ] **Step 1: Write the failing test**

```python
# apps/api/tests/test_yandex_auth_scraper.py — add at the end of the file

from app.scraper.yandex_auth import _looks_like_code_screen


def test_looks_like_code_screen_detects_push_code_heading():
    html = "<html><h1>Введите код из пуш-уведомления</h1></html>"
    assert _looks_like_code_screen(html) is True


def test_looks_like_code_screen_detects_generic_confirmation_wording():
    html = "<html><p>Введите код подтверждения, который мы отправили</p></html>"
    assert _looks_like_code_screen(html) is True


def test_looks_like_code_screen_false_for_password_screen():
    html = "<html><h1>Введите пароль</h1></html>"
    assert _looks_like_code_screen(html) is False


def test_login_with_password_without_credentials_short_circuits(tmp_path):
    from app.models.enums import SessionStatus
    from app.scraper.yandex_auth import YandexAuthScraper

    status, message = YandexAuthScraper().login_with_password("", "", str(tmp_path / "state.json"))
    assert status == SessionStatus.missing
    assert "YANDEX_OPERATOR_LOGIN" in message
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd apps/api && pytest tests/test_yandex_auth_scraper.py -v`
Expected: FAIL — `ImportError: cannot import name '_looks_like_code_screen'`.

- [ ] **Step 3: Implement the scraper method**

In `apps/api/app/scraper/yandex_auth.py`, add the import and module-level marker list at the top:

```python
from typing import Callable

from pathlib import Path

from playwright.sync_api import sync_playwright

from app.models.enums import SessionStatus
from app.scraper.debug_artifacts import save_debug_artifacts
from app.scraper.types import ScrapeResult
from app.scraper.yandex_public import CAPTCHA_MARKERS, YandexPublicScraper

# Substrings that show up on Passport's push/SMS confirmation-code screen —
# checked in lowercase against page.content(). Deliberately generic (not tied
# to push vs SMS wording) since Yandex picks the channel, not us.
_CODE_SCREEN_MARKERS = ("код из", "введите код", "код подтверждения")


def _looks_like_code_screen(html: str) -> bool:
    """True once Passport is asking for a confirmation code (push or SMS).
    Pure text check — testable without a live page, mirrors the existing
    CAPTCHA_MARKERS pattern in this module."""
    if not isinstance(html, str):
        return False
    lowered = html.lower()
    return any(marker in lowered for marker in _CODE_SCREEN_MARKERS)
```

Then, inside `YandexAuthScraper`, add class constants and the new method (after `login`, before `login_manual`):

```python
    LOGIN_PLACEHOLDER = "Логин или email"
    NEXT_BUTTON_TEXT = "Далее"
    CONTINUE_BUTTON_TEXT = "Продолжить"

    def _passport_challenge(self, page) -> tuple[SessionStatus, str] | None:
        """Bot-wall/captcha check at a login checkpoint — same markers as the
        rest of the codebase, never bypassed."""
        html = page.content()
        if any(marker.lower() in html.lower() for marker in CAPTCHA_MARKERS):
            return SessionStatus.needs_manual_action, "Captcha or bot check detected during login"
        return None

    @staticmethod
    def _fill_code(page, code: str) -> None:
        """Passport renders the confirmation code as either one input or one
        box per digit; fill whichever is present."""
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
                    page.wait_for_timeout(1500)

                    challenge = self._passport_challenge(page)
                    if challenge:
                        return challenge

                    page.locator('input[type="password"]').first.fill(password)
                    page.get_by_role("button", name=self.NEXT_BUTTON_TEXT).click()
                    page.wait_for_timeout(2000)

                    challenge = self._passport_challenge(page)
                    if challenge:
                        return challenge

                    if _looks_like_code_screen(page.content()):
                        if request_code is None:
                            return (
                                SessionStatus.needs_manual_action,
                                "Confirmation code required but no code channel was configured",
                            )
                        code = request_code()
                        if not code:
                            return SessionStatus.needs_manual_action, "Timed out waiting for the confirmation code"

                        self._fill_code(page, code)
                        page.get_by_role("button", name=self.CONTINUE_BUTTON_TEXT).click()
                        page.wait_for_timeout(2000)

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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd apps/api && pytest tests/test_yandex_auth_scraper.py -v`
Expected: all PASS.

- [ ] **Step 5: Run the full API test suite**

Run: `cd apps/api && pytest -v`
Expected: all PASS (this confirms the `login()`/`login_manual()` methods and their existing tests are untouched).

- [ ] **Step 6: Commit**

```bash
git add apps/api/app/scraper/yandex_auth.py apps/api/tests/test_yandex_auth_scraper.py
git commit -m "feat(scraper): add YandexAuthScraper.login_with_password (password + confirmation code)"
```

**Note for whoever runs this live:** the exact Playwright locators (`get_by_placeholder("Логин или email")`, `input[type="password"]`, button text `"Далее"`/`"Продолжить"`, and the `_CODE_SCREEN_MARKERS` wording) are based on the current Passport UI and cannot be verified by this test suite — no test here drives a real page. Run `python -m scripts.sprav_login` alongside a manual trigger of `login_operator()` against the real site once this lands, and adjust the locators/markers if Passport's copy or layout differs from what's coded here. A captcha/bot-wall or an unrecognized markup at any step degrades safely to `needs_manual_action` — it does not hang or crash.

---

### Task 4: API — `POST /api/scraper/yandex/session/code`

**Files:**
- Modify: `apps/api/app/schemas/scraper_session.py`
- Modify: `apps/api/app/api/scraper_sessions.py`
- Create: `apps/api/tests/test_yandex_code_login.py`
- Modify: `apps/api/tests/test_scrape_endpoints_require_admin.py`

**Interfaces:**
- Consumes: `ScrapeService.submit_code` (Task 2), `SessionStatus.awaiting_code` (Task 1).
- Produces: `POST /api/scraper/yandex/session/code` — 200 `SessionStatusResponse` on success, 409 when not `awaiting_code`, 401 anonymous, 403 non-admin.

- [ ] **Step 1: Write the failing tests**

```python
# apps/api/tests/test_yandex_code_login.py
"""POST /api/scraper/yandex/session/code — the operator's confirmation-code
submission endpoint (Yandex password+confirmation-code login)."""

from app.models.enums import SessionStatus
from app.services.scrape_service import ScrapeService


def test_submit_code_succeeds_when_awaiting_code(admin_client, db_session):
    service = ScrapeService(db_session)
    session = service.get_session_record()
    session.status = SessionStatus.awaiting_code
    db_session.commit()

    resp = admin_client.post("/api/scraper/yandex/session/code", json={"code": "123456"})

    assert resp.status_code == 200
    assert resp.json()["status"] == "awaiting_code"
    db_session.refresh(session)
    assert session.pending_code == "123456"


def test_submit_code_rejects_when_no_login_in_progress(admin_client, db_session):
    resp = admin_client.post("/api/scraper/yandex/session/code", json={"code": "123456"})
    assert resp.status_code == 409


def test_submit_code_rejects_non_digit_code(admin_client, db_session):
    service = ScrapeService(db_session)
    session = service.get_session_record()
    session.status = SessionStatus.awaiting_code
    db_session.commit()

    resp = admin_client.post("/api/scraper/yandex/session/code", json={"code": "abc123"})
    assert resp.status_code == 422


def test_submit_code_never_echoes_pending_code(admin_client, db_session):
    service = ScrapeService(db_session)
    session = service.get_session_record()
    session.status = SessionStatus.awaiting_code
    db_session.commit()

    resp = admin_client.post("/api/scraper/yandex/session/code", json={"code": "123456"})
    assert "123456" not in resp.text
```

```python
# apps/api/tests/test_scrape_endpoints_require_admin.py — add at the end of the file

def test_session_code_rejects_anonymous(client):
    resp = client.post("/api/scraper/yandex/session/code", json={"code": "123456"})
    assert resp.status_code == 401


def test_session_code_rejects_review_operator(operator_client):
    resp = operator_client.post("/api/scraper/yandex/session/code", json={"code": "123456"})
    assert resp.status_code == 403
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd apps/api && pytest tests/test_yandex_code_login.py tests/test_scrape_endpoints_require_admin.py -v`
Expected: FAIL — `404 Not Found` for the new route.

- [ ] **Step 3: Add the request schema**

In `apps/api/app/schemas/scraper_session.py`:

```python
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import SessionStatus


class SessionStatusResponse(BaseModel):
    status: SessionStatus
    last_login_at: datetime | None = None
    last_checked_at: datetime | None = None
    storage_state_path: str | None = None
    message: str | None = None


class LoginResponse(BaseModel):
    status: SessionStatus | str
    message: str


class CodeSubmission(BaseModel):
    # Yandex confirmation codes are short numeric strings; digits-only keeps
    # arbitrary text away from the Playwright fill() call downstream.
    code: str = Field(min_length=1, max_length=12, pattern=r"^\d+$")
```

- [ ] **Step 4: Add the route**

In `apps/api/app/api/scraper_sessions.py`:

```python
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.core.database import SessionLocal, get_db
from app.models.enums import SessionStatus
from app.schemas.scraper_session import CodeSubmission, LoginResponse, SessionStatusResponse
from app.services.scrape_service import ScrapeService
```

(only the `HTTPException` import and `CodeSubmission` are new — keep the rest of the file's existing imports/functions as-is). Add the route after `check_session`:

```python
@router.post("/session/code", response_model=SessionStatusResponse)
def submit_session_code(
    payload: CodeSubmission,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin),
) -> SessionStatusResponse:
    """Deliver the operator's confirmation code to a login that's paused in
    awaiting_code, waiting on ScrapeService._request_code's poll loop."""
    service = ScrapeService(db)
    session = service.get_session_record()
    if session.status != SessionStatus.awaiting_code:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="No pending confirmation code request")
    session = service.submit_code(payload.code)
    return _to_status_response(session)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd apps/api && pytest tests/test_yandex_code_login.py tests/test_scrape_endpoints_require_admin.py -v`
Expected: all PASS.

- [ ] **Step 6: Run the full API test suite**

Run: `cd apps/api && pytest -v`
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add apps/api/app/schemas/scraper_session.py apps/api/app/api/scraper_sessions.py apps/api/tests/test_yandex_code_login.py apps/api/tests/test_scrape_endpoints_require_admin.py
git commit -m "feat(api): add POST /scraper/yandex/session/code"
```

---

### Task 5: Frontend contract — types + API client

**Files:**
- Modify: `apps/web/lib/types.ts`
- Modify: `apps/web/lib/api.ts`

**Interfaces:**
- Consumes: `POST /api/scraper/yandex/session/code` (Task 4).
- Produces: `SessionStatus` (TS union, now including `"pending"` and `"awaiting_code"`), `submitSessionCode(code: string): Promise<SessionInfo>`.

- [ ] **Step 1: Extend the `SessionStatus` union**

In `apps/web/lib/types.ts`, replace the existing union (it was already missing `"pending"`, a pre-existing gap this feature also needs closed since the new UI must render both intermediate states):

```typescript
export type SessionStatus =
  | "missing"
  | "valid"
  | "expired"
  | "needs_manual_action"
  | "pending"
  | "awaiting_code";
```

- [ ] **Step 2: Add the API client function**

In `apps/web/lib/api.ts`, immediately after `checkSession`:

```typescript
export async function submitSessionCode(code: string): Promise<SessionInfo> {
  return request<SessionInfo>("/api/scraper/yandex/session/code", {
    method: "POST",
    body: JSON.stringify({ code }),
  });
}
```

- [ ] **Step 3: Type-check**

Run: `cd apps/web && npm run lint`
Expected: no new errors (this task only adds a type and a function; nothing calls `submitSessionCode` yet, so no unused-symbol issues since it's exported).

- [ ] **Step 4: Commit**

```bash
git add apps/web/lib/types.ts apps/web/lib/api.ts
git commit -m "feat(web): add submitSessionCode and awaiting_code/pending session states"
```

---

### Task 6: Frontend — Yandex connection card on `/settings`

**Files:**
- Create: `apps/web/components/settings/yandex-connection.tsx`
- Modify: `apps/web/app/(dashboard)/settings/page.tsx`

**Interfaces:**
- Consumes: `getSession`, `loginYandex`, `checkSession`, `submitSessionCode` (Task 5's `lib/api.ts`), `SessionInfo`/`SessionStatus` (Task 5's `lib/types.ts`).
- Produces: `YandexConnection` React component (no props — it owns its own session state and polling).

- [ ] **Step 1: Write the component**

```tsx
// apps/web/components/settings/yandex-connection.tsx
"use client";

import { useEffect, useRef, useState } from "react";
import { checkSession, getSession, loginYandex, submitSessionCode } from "@/lib/api";
import type { SessionInfo, SessionStatus } from "@/lib/types";

const STATUS_LABEL: Record<SessionStatus, string> = {
  missing: "Не подключено",
  valid: "Подключено",
  expired: "Сессия устарела",
  needs_manual_action: "Требуется ручной вход",
  pending: "Выполняется вход…",
  awaiting_code: "Ожидает код подтверждения",
};

const POLL_INTERVAL_MS = 2000;

export function YandexConnection() {
  const [session, setSession] = useState<SessionInfo | null>(null);
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  function stopPolling() {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }

  function startPolling() {
    stopPolling();
    pollRef.current = setInterval(async () => {
      try {
        const info = await getSession();
        setSession(info);
        if (info.status !== "pending" && info.status !== "awaiting_code") {
          stopPolling();
        }
      } catch {
        stopPolling();
      }
    }, POLL_INTERVAL_MS);
  }

  useEffect(() => {
    getSession()
      .then((info) => {
        setSession(info);
        if (info.status === "pending" || info.status === "awaiting_code") {
          startPolling();
        }
      })
      .catch((err) => setError((err as Error).message));
    return stopPolling;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function handleStartLogin() {
    setError(null);
    setBusy(true);
    try {
      await loginYandex();
      startPolling();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function handleSubmitCode(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const info = await submitSessionCode(code);
      setSession(info);
      setCode("");
      startPolling();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function handleCheck() {
    setError(null);
    setBusy(true);
    try {
      const info = await checkSession();
      setSession(info);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const status = session?.status ?? "missing";

  return (
    <div className="max-w-md space-y-3 rounded border border-border bg-surface p-4">
      <div>
        <h2 className="text-sm font-medium">Подключение к Яндексу</h2>
        <p className="text-xs text-text-dim">
          Статус: <strong className="text-text">{STATUS_LABEL[status]}</strong>
        </p>
        {session?.last_login_at && (
          <p className="text-xs text-text-dim">Последний вход: {new Date(session.last_login_at).toLocaleString("ru-RU")}</p>
        )}
      </div>

      {status === "awaiting_code" && (
        <form onSubmit={handleSubmitCode} className="space-y-2">
          <label htmlFor="yandex-code" className="block text-xs font-medium">
            Код подтверждения
          </label>
          <input
            id="yandex-code"
            type="text"
            inputMode="numeric"
            value={code}
            onChange={(e) => setCode(e.target.value)}
            className="w-40 rounded border border-border bg-bg px-2 py-1 text-sm"
            data-testid="yandex-code-input"
          />
          <button
            type="submit"
            disabled={busy || code.length === 0}
            className="rounded bg-accent px-3 py-1.5 text-xs font-semibold text-black disabled:opacity-50"
            data-testid="yandex-code-submit"
          >
            Подтвердить
          </button>
        </form>
      )}

      {error && <div className="text-sm text-bad">{error}</div>}

      <div className="flex gap-2">
        <button
          type="button"
          onClick={handleStartLogin}
          disabled={busy || status === "pending" || status === "awaiting_code"}
          className="rounded bg-accent px-3 py-1.5 text-xs font-semibold text-black disabled:opacity-50"
          data-testid="yandex-start-login"
        >
          Начать авторизацию
        </button>
        <button
          type="button"
          onClick={handleCheck}
          disabled={busy}
          className="rounded border border-border px-3 py-1.5 text-xs font-semibold disabled:opacity-50"
          data-testid="yandex-check-session"
        >
          Проверить
        </button>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Mount it on the Settings page**

In `apps/web/app/(dashboard)/settings/page.tsx`:

```tsx
"use client";

import { useEffect, useState } from "react";
import { getSettings } from "@/lib/api";
import type { Settings } from "@/lib/types";
import { SettingsForm } from "@/components/settings/settings-form";
import { YandexConnection } from "@/components/settings/yandex-connection";

export default function SettingsPage() {
  const [settings, setSettings] = useState<Settings | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getSettings()
      .then(setSettings)
      .catch((err) => setError((err as Error).message));
  }, []);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Настройки</h1>
        <p className="text-sm text-text-dim">Параметры дашборда</p>
      </div>

      {error && <div className="text-sm text-bad">{error}</div>}
      {settings && <SettingsForm initial={settings} />}
      <YandexConnection />
    </div>
  );
}
```

- [ ] **Step 3: Lint**

Run: `cd apps/web && npm run lint`
Expected: no errors.

- [ ] **Step 4: Manual smoke test**

Run: `docker compose up --build` (or `npm run dev` in `apps/web` + `uvicorn app.main:app --reload` in `apps/api`), then open `http://localhost:3000/settings`, log in as an admin user, and confirm:
- The "Подключение к Яндексу" card renders with a status label.
- Clicking "Начать авторизацию" flips the status to "Выполняется вход…" and the button disables.
- If/when the flow reaches the confirmation-code screen, the code input appears; submitting a code (or an intentionally wrong one, to observe the failure path) is reflected in the status within ~2s.
- "Проверить" updates the status without starting a new login.

- [ ] **Step 5: Commit**

```bash
git add apps/web/components/settings/yandex-connection.tsx apps/web/app/\(dashboard\)/settings/page.tsx
git commit -m "feat(web): add Yandex connection card to Settings"
```

---

## Self-Review Notes

- **Spec coverage:** data model (Task 1) → service polling/`submit_code` (Task 2) → scraper automation (Task 3) → API endpoint (Task 4) → frontend contract (Task 5) → Settings UI card (Task 6) covers every component listed in the design doc's "Components" section. The design's "Error handling / edge cases" (concurrent-login no-op, timeout → `needs_manual_action`, captcha at any step, `pending_code` never logged/returned) are covered by Task 2's polling tests, Task 3's challenge checks at every step, and Task 4's `test_submit_code_never_echoes_pending_code`. The design's explicit "Out of scope" items (captcha solving, moving credentials into the DB/UI, removing `sprav_login.py`, automatic scheduled expiry checks) are correctly not implemented anywhere in this plan.
- **Placeholder scan:** no TBD/TODO; every step has literal code and exact commands.
- **Type consistency:** `login_with_password(login, password, storage_state_path, request_code=None) -> tuple[SessionStatus, str]` is the same signature in Task 3's implementation and every place it's referenced (Task 2's `login_operator`, Task 2/3's stubs and tests). `submit_code(code: str) -> ScraperSession` matches between Task 2's implementation, Task 4's route, and Task 4's tests. `SessionInfo`/`SessionStatus` match between Task 4's `SessionStatusResponse`/`CodeSubmission` and Task 5/6's frontend types and usage.
