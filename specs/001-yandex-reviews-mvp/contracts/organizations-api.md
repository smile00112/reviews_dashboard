# Contract: Organizations API

**Base path**: `/api/organizations`

## GET /api/organizations

List all organizations with last scrape summary.

**Response 200**:

```json
{
  "items": [
    {
      "id": "uuid",
      "name": "string | null",
      "yandex_url": "string",
      "normalized_url": "string",
      "external_id": "string | null",
      "address": "string | null",
      "rating": "number | null",
      "review_count": "integer | null",
      "preferred_scrape_mode": "public | operator_auth",
      "last_successful_scrape_at": "ISO8601 | null",
      "last_scrape_status": "pending | running | success | failed | needs_manual_action",
      "created_at": "ISO8601",
      "updated_at": "ISO8601"
    }
  ]
}
```

## POST /api/organizations

Create organization.

**Request body**:

```json
{
  "yandex_url": "https://yandex.ru/maps/org/...",
  "preferred_scrape_mode": "public"
}
```

**Response 201**: Organization object (same shape as list item).

**Response 422**: Invalid URL validation error.

## GET /api/organizations/{organization_id}

**Response 200**: Single organization object.

**Response 404**: Not found.

## PATCH /api/organizations/{organization_id}

**Request body** (partial):

```json
{
  "preferred_scrape_mode": "operator_auth",
  "name": "Display override"
}
```

**Response 200**: Updated organization.

## DELETE /api/organizations/{organization_id}

**Response 204**: Deleted.

**Response 404**: Not found.
