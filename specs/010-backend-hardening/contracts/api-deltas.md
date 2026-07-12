# API Contract Deltas: Backend Hardening (010)

No new endpoints. No request/response **shape** changes. Semantic deltas only.

## POST /api/scraper/yandex/login — `202 Accepted`

- **Before**: 202 returned only after the full Playwright login ran inline (tens of seconds).
- **After**: returns immediately. `LoginResponse.status` is `pending` when work was scheduled (or the current status if a login/check is already `pending` — no duplicate scheduling). Terminal outcome observed via polling `GET /api/scraper/yandex/session`.
- `LoginResponse.message`: human-readable ("Login scheduled" / "Login already in progress").

## POST /api/scraper/yandex/session/check — `200 OK` → `202 Accepted`

- **Before**: blocked inline on Playwright; returned final status.
- **After**: `status_code=202`; returns session with `status=pending` immediately; result via polling `GET /session`. (Status-code change is the one visible contract change; the response model `SessionStatusResponse` is unchanged. `apps/web` does not currently call this endpoint's status code conditionally — verified no frontend change needed.)

## GET /api/scraper/yandex/session

- May now return `status: "pending"` (new `SessionStatus` value). While `pending`, file-existence heuristics do not overwrite the status.

## POST /api/scrape/all → parent ScrapeRun

- **Before**: parent run always terminal `success`, counters 0.
- **After**: parent `status` aggregates children (`failed` / `needs_manual_action` / `success` per FR-004); parent `reviews_seen/inserted/updated` are sums of children. `ScrapeRunResponse` shape unchanged.

## All scrape runs

- `reviews_inserted` / `reviews_updated` now guaranteed to equal actual DB effects (FR-002).

## GET /api/companies

- Response identical; `branch_count` now computed by a single grouped query (perf only).

## GET /api/dashboard/overview

- Payload identical; internal query count reduced (perf only).

## Startup behavior

- Empty `API_CORS_ORIGINS` now aborts startup with an explicit error instead of serving `allow_origins=["*"]` with credentials.
