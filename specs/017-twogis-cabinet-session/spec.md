# Feature 017 — 2GIS cabinet session (cookie storage + check)

**Status:** design
**Date:** 2026-07-23
**Depends on:** `scraper_sessions` table (feature 010), `cookie_import.py` (Yandex manual import)

## Summary

Store and verify an operator's **2GIS business-cabinet** session (`account.2gis.com`), by
analogy with the existing Yandex operator session. The cabinet authenticates with a **Bearer
access token** (not cookies — see findings). Scope for now is deliberately narrow:

- **Save** the cabinet token (manual import, analogous to the Yandex cookie import).
- **Check** the saved token against the live cabinet API (`GET /users`).
- A **CLI validator** to confirm the token works + pull one point's data.

The stored session is **not consumed by any scraper or job yet** — it is plumbing for future
2GIS-cabinet work. No nightly job, no DB import of cabinet data, no auto-login.

## Background / findings from the spike (confirmed live, HTTP 200)

- The cabinet is a React SPA at `https://account.2gis.com/`; its backend API (read from the
  SPA's `window.APP_CONFIG`) is **`https://api.account.2gis.com/api/1.0`**.
  - `GET /users` → current user (has `email`, `orgs`). Clean **session-validity check** endpoint.
  - `GET /orgs?fields=orgDetails` → org list under `result.items[]` ("collect a point").
- **Auth is a Bearer access token, NOT cookies.** The SPA sends
  `Authorization: Bearer <access token>` plus a static `x-api-key: accweb96f8` (the
  `lkApiKeyWeb` from `APP_CONFIG`). The `spid` cookie plays no part (a `spid`-only request is
  401/400). Confirmed against a real operator token: `/users` and `/orgs` both return **200**
  with real data. The token is short-lived, so an expired one → `expired` (re-import).
  → The operator pastes the **`Authorization` value** copied from a DevTools request to
  `api.account.2gis.com` (Network tab → Request Headers). A raw `Bearer …` line or the bare
  token are both accepted.
- The **API host `api.account.2gis.com` is reachable directly** even from a foreign IP (only
  the SPA/`/external/userstatus` is geo-walled), so the check needs no proxy and works from
  the server. No cookie/`spid` handling is needed at all.

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

### Token import — `extract_bearer_token`
2GIS uses no cookies, so `cookie_import.py` is left untouched (Yandex-only). A small
`extract_bearer_token(text)` in `scraper/twogis_account.py` pulls the access token out of
whatever the operator pastes — a full request-headers block, an `Authorization: Bearer …`
line, or the bare token (regex: a `Bearer <token>` match, else a lone `[A-Za-z0-9._-]{20,}`
line). The token is stored in the session's storage-state file as `{"access_token": "…"}`.
An empty paste or one with no token → `ValueError` (→ 422) before any file write.

### Cabinet client — new `scraper/twogis_account.py` (requests-based)
No Playwright. Loads the token from the storage-state file and calls the cabinet API directly
with `Authorization: Bearer <token>` + `x-api-key`. Never raises out of an attempt (IV); the
token never appears in messages/logs (VIII).

- `check_session(storage_state_path) -> (SessionStatus, message)`:
  no token ⇒ `missing`; `GET /users` → 200 ⇒ `valid` (message includes the operator email);
  400/401/403 ⇒ `expired`; network/other ⇒ `needs_manual_action`.
- `list_orgs(storage_state_path, limit=1) -> list[dict]`: `GET /orgs?fields=orgDetails`, reads
  `result.items[]`, returns a trimmed value-only view (id / name / address / branchesCount) for
  the CLI. Display-only.

Constants: `ACCOUNT_API = "https://api.account.2gis.com/api/1.0"`; `x-api-key` from
`settings.twogis_lk_api_key` (default `accweb96f8`). Headers include `Origin`/`Referer` =
`https://account.2gis.com`, `locale: ru`.

### Service — new `TwogisAccountService`
Dedicated service (leaves the delicate Yandex Playwright/login/awaiting-code logic in
`ScrapeService` untouched). Manages the `provider="2gis"` row:

- `get_session_status()` — file-heuristic refresh mirroring `ScrapeService.get_session_status`
  (valid+no-file ⇒ missing; missing+file ⇒ valid), minus the `pending`/`awaiting_code` guards.
- `import_session_cookies(text)` — `extract_bearer_token`, write `{"access_token": …}`, mark
  `valid` optimistically, stamp `last_login_at`/`last_checked_at`, message "Token imported —
  press Проверить to verify". (Name kept for symmetry with the Yandex session API; payload is a
  token.)
- `check_session()` — call the cabinet client, persist status + `last_checked_at` + message.

All synchronous (the check is one fast HTTP call — **no BackgroundTasks**).

### API — new router `api/twogis_account.py`, prefix `/api/scraper/2gis`
- `POST /session/import` → 200 `SessionStatusResponse` (422 only on empty/unparseable paste).
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

Exit codes: 0 valid, 2 needs_manual_action, 1 missing/expired. Never prints the token or
storage-state contents — only status, message, path, and the org's public fields.

### Web — Settings UI (parity with Yandex)
- `components/settings/twogis-cookie-import.tsx` — manual import panel; instructions to copy the
  `authorization` request-header value from a DevTools request to `api.account.2gis.com`. Accepts
  a `Bearer …` line or the bare token.
- `components/settings/twogis-connection.tsx` — status label + "Проверить" button + the import
  panel. No login button (no auto-login), no code modal.
- `lib/api.ts` — `importTwogisSessionCookies`, `getTwogisSession`, `checkTwogisSession`.
- `app/(dashboard)/settings/page.tsx` — render `<TwogisConnection />` under `<YandexConnection />`.

## Testing (critical-path per constitution)

- `test_twogis_account_service.py` — `extract_bearer_token` (Bearer line / bare / headers block /
  absent); import writes `{"access_token": …}` + marks valid, rejects a token-less paste without
  writing; check maps 200→valid / expired / needs_manual_action (cabinet client mocked); 2gis and
  yandex are independent rows. No live HTTP.
- `test_twogis_account_api.py` — import 422 on a token-less paste, never echoes the token; GET/POST
  session contract; permission gate (401). `cookie_import.py` and its tests are untouched (Yandex).

Cabinet HTTP is always mocked in tests (no network, no real token committed).

## Notes

- **Token lifetime.** The cabinet access token is short-lived; when it expires the check returns
  `expired` and the operator re-imports a fresh one. A refresh flow (exchanging `dg_refresh_token`
  / `spid` via `api.auth.2gis.com`) is deliberately out of scope for this "save + check" feature.
- **Confirmed live:** `/users` and `/orgs` both returned HTTP 200 with a real operator token; the
  API host is reachable directly (no proxy, no geo-wall on the API itself).
