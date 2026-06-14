# Contract: Scrape API

**Base path**: `/api/organizations/{organization_id}/scrape`, `/api/scrape/all`, `/api/scrape-runs`

## POST /api/organizations/{organization_id}/scrape

Start scrape for one organization (background task).

**Request body**:

```json
{
  "mode": "public"
}
```

`mode`: `public` | `operator_auth` — defaults to organization `preferred_scrape_mode` if omitted.

**Response 202**:

```json
{
  "scrape_run_id": "uuid",
  "status": "queued"
}
```

**Response 404**: Organization not found.

**Response 409**: Scrape already running for organization (optional guard).

## POST /api/scrape/all

Start scrape for all organizations.

**Request body**:

```json
{
  "mode": "public"
}
```

**Response 202**:

```json
{
  "scrape_run_id": "uuid",
  "status": "queued",
  "organization_count": 5
}
```

Parent run has `organization_id: null`; child runs per organization MAY be created (implementation detail).

## GET /api/scrape-runs

Recent scrape runs.

**Query parameters**: `limit` (default 50), `offset`, optional `organization_id`

**Response 200**:

```json
{
  "items": [
    {
      "id": "uuid",
      "organization_id": "uuid | null",
      "mode": "public | operator_auth",
      "status": "queued | running | success | failed | needs_manual_action",
      "started_at": "ISO8601",
      "finished_at": "ISO8601 | null",
      "reviews_seen": 0,
      "reviews_inserted": 0,
      "reviews_updated": 0,
      "error_code": "string | null",
      "error_message": "string | null",
      "debug_screenshot_path": "string | null",
      "debug_html_path": "string | null"
    }
  ]
}
```

## GET /api/scrape-runs/{run_id}

**Response 200**: Single scrape run object (same shape as list item).

**Response 404**: Not found.

## Health

## GET /health

**Response 200**: `{ "status": "ok" }`
