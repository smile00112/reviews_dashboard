# Contract: Reviews API

**Base path**: `/api/reviews` and `/api/organizations/{organization_id}/reviews`

## GET /api/reviews

Global reviews feed with filters.

**Query parameters**:

| Param | Type | Description |
|-------|------|-------------|
| organization_id | uuid | Filter by organization |
| rating | integer (1-5) | Filter by star rating |
| date_from | ISO date | Minimum review_date |
| date_to | ISO date | Maximum review_date |
| new_only | boolean | Reviews first seen since last scrape window (implementation-defined cutoff) |
| limit | integer | Pagination, default 50 |
| offset | integer | Pagination, default 0 |

**Sort**: `review_date DESC NULLS LAST`, then `first_seen_at DESC`

**Response 200**:

```json
{
  "items": [
    {
      "id": "uuid",
      "organization_id": "uuid",
      "organization_name": "string | null",
      "source": "yandex_maps",
      "scrape_mode": "public | operator_auth",
      "author_name": "string | null",
      "rating": 1,
      "review_text": "string",
      "review_date_text": "string | null",
      "review_date": "ISO8601 | null",
      "response_text": "string | null",
      "first_seen_at": "ISO8601",
      "last_seen_at": "ISO8601"
    }
  ],
  "total": 0,
  "limit": 50,
  "offset": 0
}
```

## GET /api/organizations/{organization_id}/reviews

Paginated reviews for one organization. Same query params except `organization_id` is implicit from path.

**Response 200**: Same paginated shape as global endpoint.

**Response 404**: Organization not found.
