# API Contract: HTTP Scrape (public_http mode)

**Feature**: `003-http-scraper`

No new endpoints. The existing scrape API accepts the new mode.

## POST /api/organizations/{id}/scrape  (existing, extended)

Request body (existing `ScrapeRequest`):

```json
{ "mode": "public_http" }
```

- `mode` now accepts `public` | `operator_auth` | `public_http`.
- **202** `{ "scrape_run_id": "…", "status": "queued" }` — runs in background, identical to other modes.
- **404** organization not found.
- Execution: `ScrapeService` routes `public_http` to `YandexHttpScraper`; reviews persist via
  `upsert_reviews` (dedup + analytics); a `ScrapeRun` records the outcome.

## GET /api/scrape-runs/{run_id}  (existing, unchanged)

Used by the dedicated page to poll status. A `public_http` run reports:

- `mode`: `public_http`
- `status`: `queued | running | success | failed | needs_manual_action`
- on success: `reviews_seen / reviews_inserted / reviews_updated`
- on bot-protection: `status=needs_manual_action`, `error_code` set, `debug_html_path` populated.

## GET /api/organizations/{id}/reviews  (existing, unchanged)

Used by the page to display the org's reviews after the run completes. Reviews scraped via
HTTP appear with `scrape_mode=public_http` and feature-002 analysis fields.

## Behavior guarantees

- The HTTP scraper performs no captcha bypass; a challenge → `needs_manual_action`.
- Existing `public` / `operator_auth` requests are unaffected.
- HTTP-scraped reviews dedup against existing reviews of the same organization by `content_hash`.
