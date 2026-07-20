# Yandex password + confirmation-code login — design

**Date:** 2026-07-20
**Status:** approved (brainstorming), pending implementation plan

## Goal

Make the `operator_auth` login actually work end-to-end from the web dashboard:
operator clicks a button in **Settings**, the backend drives Passport
(login → password → push/SMS confirmation code) with Playwright, the operator
types the confirmation code into a Settings form field when prompted, and the
resulting `Session_id` cookie is saved to the existing storage-state file. A
"Проверить" button in the same card re-validates a saved session for staleness.

This replaces the currently-broken `YandexAuthScraper.login()` automated path
(its CSS selectors no longer match Passport's React markup, so it always
returns `needs_manual_action`) with a working one, while leaving the existing
manual fallback (`scripts/sprav_login.py`, headed browser, operator clicks
everything by hand) untouched as the escape hatch when automation can't get
through (captcha, unexpected markup, etc.).

## Context

### Why this now

The web UI (`/organizations`) already has a "Войти" button and session-status
widget wired to `POST /api/scraper/yandex/login` / `GET /session`
(feature 010), but the login it triggers is dead code in practice — `login()`
was written against selectors (`input[name="login"]`) that don't exist in the
current Passport flow. Operators currently must run
`python -m scripts.sprav_login` locally and sign in by hand. The goal is to
make the button-driven path real, with the one piece that genuinely requires a
human — the confirmation code — surfaced in the dashboard instead of a
terminal.

### Existing infrastructure reused

- `ScraperSession` model / `SessionStatus` enum, the `pending` status pattern
  and `mark_session_pending()` (feature 010) — the same "202 now, poll `GET
  /session` for the terminal state" shape extends naturally to a new
  intermediate state.
- `app/scraper/markers.py` `BOT_MARKERS`, and the existing challenge-detection
  pattern in `yandex_auth.py`/`yandex_public.py` — reused as-is, no new bot
  detection logic.
- `app/scraper/debug_artifacts.py` for failure diagnostics.
- The `/settings` page + `SettingsForm` pattern (`getSettings`/`updateSettings`,
  `lib/api.ts` `request<T>` wrapper) for the new UI card.
- `lib/api.ts` already exports `getSession` / `loginYandex` / `checkSession`
  and `SessionInfo` in `lib/types.ts` — only a `submitSessionCode` addition and
  a new `status` value are needed on the frontend contract.

## Constraints

- **Credentials stay in env.** `YANDEX_OPERATOR_LOGIN` / `YANDEX_OPERATOR_PASSWORD`
  are read from settings/env as today; the web UI never collects or displays
  them. Only the one-time confirmation code — not a durable credential — is
  ever accepted from the browser, and it is consumed and cleared immediately
  after use, never logged.
- **No captcha/bot-wall bypass.** Any captcha or bot-wall marker at any step of
  the flow ends the attempt as `needs_manual_action` with debug artifacts
  saved — never a silent retry, never an attempt to work around it.
- **Read-only.** This feature only authenticates; it performs no writes on
  Yandex properties.
- **Scraper layer stays DB-free.** `app/scraper/*` must not import SQLAlchemy
  or touch the database (existing architecture rule) — the code-waiting logic
  is injected into the scraper as a plain callback, owned by `ScrapeService`.

## Components

### 1. Data model

- `SessionStatus` gains `awaiting_code` — browser is open and waiting for the
  operator to submit the confirmation code shown by Passport.
- `ScraperSession` gains `pending_code: str | None` — the one-time code,
  written by the API when the operator submits it and consumed (read + cleared
  to `None`) by the background login the moment it's picked up.
- Migration `0019_session_awaiting_code.py`: additive —
  `ALTER TYPE session_status_enum ADD VALUE IF NOT EXISTS 'awaiting_code'`
  (autocommit block, same pattern as `0013`) + `ADD COLUMN pending_code TEXT`.

### 2. `app/scraper/yandex_auth.py` — `YandexAuthScraper.login_with_password`

New method, additive (the old `login()` stays as-is, already covered by
`test_sprav_login_cli.py`'s no-credentials short-circuit test; not called by
`ScrapeService` anymore once this lands):

```python
def login_with_password(
    self,
    login: str,
    password: str,
    storage_state_path: str,
    request_code: Callable[[], str | None] | None = None,
) -> tuple[SessionStatus, str]:
```

Flow, headless Playwright:

1. No credentials → `missing` (same short-circuit as today's `login()`).
2. `goto(PASSPORT_AUTH_URL)`. Locate the login field with **resilient
   locators** — `get_by_placeholder("Логин или email")` /
   `get_by_role("textbox", ...)` / label text — never a generated `id` or a
   `name=` attribute, since that's precisely what broke the old selectors.
   Fill login, submit.
3. After every submit: check `BOT_MARKERS`/`CAPTCHA_MARKERS` in `page.content()`
   and whether the URL is still on a Passport challenge path; any hit →
   `needs_manual_action` with debug artifacts, stop immediately.
4. Locate the password field the same resilient way, fill, submit.
5. If a confirmation-code screen appears (heading/text containing "код",
   or a code-input container is present):
   - If `request_code` is `None` (caller didn't wire one up) →
     `needs_manual_action`, "confirmation code required but no code channel
     configured".
   - Otherwise call `request_code()` — a blocking call owned by the caller.
     `None` back means "gave up" (timeout) → `needs_manual_action`. A string
     back is filled into the code input(s) (single field or per-digit boxes,
     detected at runtime) and submitted.
6. Poll for the `Session_id` cookie (`_has_session_cookie`, existing helper),
   save `storage_state`, return `valid`. No cookie after a bounded wait →
   `needs_manual_action`.

### 3. `app/services/scrape_service.py` — `ScrapeService`

- `login_operator()` now calls `login_with_password(..., request_code=self._request_code)`
  instead of the old `login()`.
- `_request_code(self) -> str | None`:
  1. Set `session.status = awaiting_code`, `pending_code = None`, commit.
  2. Poll every ~2s for up to ~5 minutes: re-query the session row; if
     `pending_code` is set, capture it, clear it to `None`, commit, return it.
  3. Timeout exhausted → return `None` (caller turns this into
     `needs_manual_action`).
- `submit_code(code: str) -> ScraperSession`: only writes `pending_code` when
  the session is currently `awaiting_code`; the API layer turns "not
  currently awaiting a code" into 409.

### 4. API — `app/api/scraper_sessions.py`

New endpoint, same admin-gated shape as `/login` and `/session/check`:

```
POST /api/scraper/yandex/session/code   { "code": "123456" }
```

- 200 with the current `SessionStatusResponse` on success.
- 409 if the session isn't `awaiting_code` (nothing to submit to).
- Basic input shape validation (non-empty, digits only, reasonable length) in
  the Pydantic request schema — this is user input reaching a Playwright
  `fill()` call.

`GET /session` needs no change beyond `SessionStatus` gaining the new value —
the frontend already polls it.

### 5. Frontend — `/settings`

A new card, e.g. `components/settings/yandex-connection.tsx`, added to the
Settings page alongside the existing SLA form:

- Status line driven by `SessionInfo.status` (missing / valid / expired /
  pending / awaiting_code / needs_manual_action), matching the existing
  Russian status copy already used on `/organizations`.
- "Начать авторизацию" button → `loginYandex()`, then poll `getSession()`
  every ~2s until a terminal status (`valid` / `needs_manual_action`) or
  `awaiting_code`.
- While `awaiting_code`: a code input + "Подтвердить" button →
  new `submitSessionCode(code)` (`POST /session/code`), keep polling.
- "Проверить" button → existing `checkSession()`.
- `last_login_at` / `last_checked_at` surfaced as-is (already on
  `SessionInfo`).

`lib/api.ts` gains `submitSessionCode`; `lib/types.ts`'s `SessionStatus` union
gains `"awaiting_code"`.

## Error handling / edge cases

- Two logins can't run concurrently — unchanged from feature 010 (`pending`
  short-circuits a second `POST /login`); `awaiting_code` is also a non-idle
  state so a second `POST /login` while awaiting a code is likewise a no-op
  with an "already in progress" message.
- Code-wait timeout ends the run as `needs_manual_action` with a message
  pointing at the CLI fallback, exactly like every other `needs_manual_action`
  outcome in this codebase.
- A captcha/bot-wall at *any* step (including right after code submission)
  is `needs_manual_action` with debug artifacts — never retried automatically.
- `pending_code` is never logged and never returned in any API response body
  (only `status`/timestamps/`storage_state_path` are, per
  `SessionStatusResponse`).

## Testing

Following the codebase's existing pattern for this area (`test_scraper_session_async.py`,
`test_sprav_login_cli.py`): the browser-driving parts of
`login_with_password` are not unit-tested against a real page (no test does
that anywhere in this codebase today); what's covered:

- `ScrapeService._request_code` / `submit_code` polling and consume-once
  behavior, using a fake clock or a short timeout, against the test DB
  session — no Playwright involved.
- API contract: `POST /session/code` 200 vs 409, admin-gating, and that
  `GET /session` reports `awaiting_code` correctly — same `admin_client` /
  `_no_real_background`-style fixtures as the existing async-session tests,
  with a stub `auth_scraper.login_with_password` standing in for Playwright.
- `YandexAuthScraper` unit tests: the no-credentials short circuit (existing,
  unchanged) and any pure helper extracted for locating/filling the code
  input(s) if that logic is non-trivial enough to warrant it.
- Real-page selector correctness can only be confirmed by running the flow
  against live Yandex Passport during implementation — flagged as a residual
  risk, not something CI can assert.

## Out of scope

- Automated captcha solving of any kind (constitution hard rule).
- Moving operator credentials into the database/UI.
- Removing or changing `scripts/sprav_login.py` (stays as the manual fallback).
- A scheduled/automatic session-expiry check (this iteration only wires the
  existing manual `/session/check` into the new Settings card).
