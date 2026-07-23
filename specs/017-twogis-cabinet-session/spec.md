# Feature 017 — 2GIS cabinet session (cookie storage + check)

**Status:** design
**Date:** 2026-07-23
**Depends on:** `scraper_sessions` table (feature 010), `cookie_import.py` (Yandex manual import)

## Summary

Store and verify an operator's **2GIS business-cabinet** session (`account.2gis.com`), by
analogy with the existing Yandex operator session. Scope for now is deliberately narrow:

- **Save** the cabinet cookies (manual import, same as Yandex).
- **Check** the saved session against the live cabinet API.
- A **CLI validator** so the operator can confirm login + pull one point's data from their
  own (RU-reachable) machine.

The stored session is **not consumed by any scraper or job yet** — it is plumbing for future
2GIS-cabinet work. No nightly job, no DB import of cabinet data, no auto-login.

## Background / findings from the spike

- The cabinet is a React SPA at `https://account.2gis.com/`; its backend API (read from the
  SPA's `window.APP_CONFIG`) is **`https://api.account.2gis.com/api/1.0`**.
  - `GET /users` → current user. Clean **session-validity check** endpoint.
  - `GET /orgs?fields=orgDetails` → the operator's organization list ("collect a point").
- **Auth is cookie-based via `dg_session_token`** (the access-token cookie named in
  `APP_CONFIG.cookie.accessToken`), *not* `spid`. A `spid`-only request returns **401** on
  `/users` and `/orgs`. `dg_session_token` is `HttpOnly`, so JSON cookie exporters /
  `document.cookie` can't see it — the operator must copy the raw **`Cookie:`** request header
  from a DevTools → Network request to `api.account.2gis.com`. This is the exact same
  constraint as Yandex's `HttpOnly` `Session_id`.
- 2GIS **geo-walls foreign IPs** (`/external/userstatus` → 451, "Возможно, у вас включён VPN").
  The check therefore only works from an RU/CIS-reachable network. Per decision, the check
  connects **directly** (no proxy); validation happens on the operator's machine via the CLI.

## Non-goals

- No Playwright / automated 2GIS login (no `pending`/`awaiting_code` flow).
- No proxy routing for the cabinet API (direct only).
- No consumer of the session (job, sync, DB import). Future features only.
- No new `SessionStatus` enum value, no DB migration.

## Design

### Storage — reuse `scraper_sessions`
`ScraperSession` already carries a `provider` column with a unique constraint. A `provider="2gis"`
row is created on demand, `storage_state_path` = new setting `twogis_storage_state_path`
(default `.local/twogis-storage-state.json`, gitignored). Reuses `SessionStatus`
(`missing / valid / expired / needs_manual_action`). No schema change.

### Cookie import — generalize `cookie_import.py`
`parse_cookie_input(text)` currently hard-codes `Session_id` / `.yandex.ru`. Add optional
params with today's Yandex values as defaults, so existing callers and tests are unchanged:

```python
def parse_cookie_input(text, *, required_cookie="Session_id", default_domain=".yandex.ru", provider_label="Yandex"): ...
```

2GIS passes `required_cookie="dg_session_token"`, `default_domain="account.2gis.com"`,
`provider_label="2ГИС"`. The error message for a missing cookie is templated from these.
`_normalise`, `_from_header` (raw `Cookie:` header), `build_storage_state`, and the sameSite
map are reused unchanged. A `spid`-only paste is **rejected** (422) with a message pointing to
the Network → Cookie-header method; the live check remains the ultimate source of truth.

### Cabinet client — new `scraper/twogis_account.py` (requests-based)
No Playwright. Loads cookies from the storage-state file into a `requests` session and calls
the cabinet API directly. Never raises out of an attempt (constitution IV); credentials never
appear in messages/logs (constitution VIII).

- `check_session(storage_state_path) -> (SessionStatus, message)`:
  `GET /users` → 200 ⇒ `valid`; 401/403 ⇒ `expired`; 451/network/other ⇒ `needs_manual_action`
  (+ terse prose message — e.g. geo-wall hint on 451).
- `list_orgs(storage_state_path, limit=1) -> list[dict]`: `GET /orgs?fields=orgDetails`, returns
  a trimmed, value-only view (id / name / address) for the CLI to print. Display-only.

Constants: `ACCOUNT_API = "https://api.account.2gis.com/api/1.0"`. Browser-ish headers with
`Origin`/`Referer` = `https://account.2gis.com`.

### Service — new `TwogisAccountService`
Dedicated service (leaves the delicate Yandex Playwright/login/awaiting-code logic in
`ScrapeService` untouched). Manages the `provider="2gis"` row:

- `get_session_status()` — file-heuristic refresh mirroring `ScrapeService.get_session_status`
  (valid+no-file ⇒ missing; missing+file ⇒ valid), minus the `pending`/`awaiting_code` guards.
- `import_session_cookies(text)` — `parse_cookie_input(..., 2gis args)`, write storage state,
  mark `valid`, stamp `last_login_at`/`last_checked_at`, message `"Session imported (N cookies)"`.
- `check_session()` — call the cabinet client, persist status + `last_checked_at` + message.

All synchronous (the check is one fast HTTP call — **no BackgroundTasks**).

### API — new router `api/twogis_account.py`, prefix `/api/scraper/2gis`
- `POST /session/import` → 200 `SessionStatusResponse` (422 on missing `dg_session_token`).
- `GET  /session` → `SessionStatusResponse`.
- `POST /session/check` → `SessionStatusResponse` (synchronous; 200, not 202).

Reuses the existing `CookieImport` / `SessionStatusResponse` schemas. All mutating routes
guarded by `require_permission("action:scraper_session.manage")`. Registered in `app/main.py`.

### CLI validator — `scripts/twogis_account_check.py`
Mirrors `scripts/sprav_login.py`. DB-free; exercises only the storage-state file + cabinet client:

```
python -m scripts.twogis_account_check          # check session + print one org
python -m scripts.twogis_account_check --check   # check only
```

Exit codes: 0 valid, 2 needs_manual_action, 1 missing/expired. Never prints cookie values or
storage-state contents — only status, message, path, and the org's public fields.

### Web — Settings UI (parity with Yandex)
- `components/settings/twogis-cookie-import.tsx` — manual import panel, 2GIS-specific
  instructions (export from `account.2gis.com`, must include `dg_session_token`, use the
  Network → `Cookie:` header method because it's `HttpOnly`).
- `components/settings/twogis-connection.tsx` — status label + "Проверить" button + the import
  panel. No login button (no auto-login), no code modal.
- `lib/api.ts` — `importTwogisSessionCookies`, `getTwogisSession`, `checkTwogisSession`.
- `app/(dashboard)/settings/page.tsx` — render `<TwogisConnection />` under `<YandexConnection />`.

## Testing (critical-path per constitution)

- `test_cookie_import.py` — extend: 2GIS args accept a `dg_session_token` header/JSON, reject a
  `spid`-only paste; **existing Yandex cases still pass** with defaults unchanged (contract).
- `test_twogis_account_service.py` — import writes storage state + marks valid; check maps
  200→valid / 401→expired / network→needs_manual_action (cabinet client mocked). No live HTTP.
- `test_twogis_account_api.py` — import 422 on missing cookie; GET/POST session contract;
  permission gate (403/401).

Cabinet HTTP is always mocked in tests (no network, no real cookies committed).

## Open risk

`dg_session_token` is the best-evidence auth cookie but was not confirmable against a live valid
session from this environment (geo-wall + dead proxy). If the live `/users` check reveals 2GIS
needs a different/additional cookie, only the `required_cookie` constant and the client's request
shape change — the structure holds.
