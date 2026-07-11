# Contract: `GET /api/dashboard/overview`

Network-level aggregated overview. Read-only. Guarded by the existing auth dependency (401 if unauthenticated). Both roles (`admin`, `review_operator`) may read.

## Request

Query parameters (all optional; defaults match prototype default state):

| Param | Type | Default | Values |
|-------|------|---------|--------|
| `period` | string | `30d` | `day` `week` `30d` `90d` `year` `all` |
| `platform` | string | `all` | `all` `yandex` `google` `gis2` |
| `org_ids` | UUID[] (repeatable) | — (all orgs) | one or more organization ids |
| `company_id` | UUID | — | restrict orgs to a company (branches) |

`org_ids` and `company_id` compose: if both given, intersect. If neither, all organizations.

## Response `200 application/json`

```jsonc
{
  "period": "30d",
  "platform": "all",
  "generated_at": "2026-07-11T09:00:00Z",
  "header": {
    "new_in_period": 312,
    "unanswered_over_24h": 12,
    "fresh_negatives_2h": 4
  },
  "kpi_hero": {
    "network_avg_rating": 4.36,
    "network_avg_rating_delta": 0.08,          // null until history accrues
    "new_in_period": 312,
    "new_today": 23,
    "total_reviews": 7706,
    "avg_per_day": 21.1,
    "unanswered_total": 210,
    "unanswered_delta_24h": 18,
    "overdue_24h": 12
  },
  "kpi_strip": {
    "response_avg_min": 22,
    "response_median_min": 14,
    "response_p95_min": 252,
    "response_approximate": true,
    "sla_percent": 87.0,
    "positivity_percent": 78.3,
    "reputation_index": 95.0
  },
  "rating_distribution": {
    "bars": [
      {"star": 5, "count": 7475, "percent": 97.0},
      {"star": 4, "count": 38, "percent": 0.5},
      {"star": 3, "count": 31, "percent": 0.4},
      {"star": 2, "count": 31, "percent": 0.4},
      {"star": 1, "count": 131, "percent": 1.7}
    ],
    "share_4_5": 97.5,
    "share_1_3": 2.5,
    "total": 7706
  },
  "sentiment": {
    "positive": 6036, "neutral": 65, "negative": 114,
    "positive_percent": 97.1, "neutral_percent": 1.0, "negative_percent": 1.8,
    "analyzed_total": 6215
  },
  "platform_breakdown": [
    {"platform": "yandex", "review_count": 2070},
    {"platform": "gis2", "review_count": 1480},
    {"platform": "google", "review_count": 4156}
  ],
  "platform_cards": [
    {"platform": "yandex", "weighted_rating": 4.44, "rating_delta": 0.07, "negativity_percent": 10.5, "response_speed_hours": 5.7},
    {"platform": "google", "weighted_rating": 4.51, "rating_delta": null, "negativity_percent": null, "response_speed_hours": null},
    {"platform": "gis2",  "weighted_rating": 4.16, "rating_delta": -0.04, "negativity_percent": 14.1, "response_speed_hours": 8.2}
  ],
  "attention": [
    {"type": "unanswered_overdue", "title": "12 отзывов без ответа > 24ч", "subtitle": "SLA нарушен", "value": 12, "severity": "urgent", "link": "/reviews?filter=overdue"},
    {"type": "fresh_negative", "title": "4 новых негативных отзыва (1–2★)", "subtitle": "за 2 часа", "value": 4, "severity": "urgent", "link": "/reviews?rating=1"},
    {"type": "escalated", "title": "3 эскалированных отзыва", "subtitle": "ждут реакции", "value": 3, "severity": "warn", "link": "/reviews?status=escalated"},
    {"type": "aspect_spike", "title": "Рост аспекта «опоздание»", "subtitle": "+42% за 7 дней", "value": 42, "severity": "warn", "link": "/reviews"}
    // rating_drop items omitted when no snapshot history
  ],
  "worst_locations": [
    {"organization_id": "…", "city": "Москва", "name": "Севастопольский", "rating": 3.78, "rating_delta": -0.22, "unanswered_count": 3}
    // ≤ 10, rating ascending
  ],
  "trending_aspects": [
    {"category": "опоздание", "mentions": 67, "change_percent": 42, "sentiment": {"pos": 14, "neu": 21, "neg": 65}}
  ]
}
```

## Rules

- Empty network → all counts `0`, arrays `[]`, deltas `null`; HTTP 200 (never 500).
- `*_delta` and `rating_delta` are `null` when snapshot history does not cover the period → UI renders "—".
- `platform_cards` fields that cannot be computed (Google/2GIS per-review) are `null` → UI renders "нет данных".
- Response-time values are minutes; `response_approximate` always `true` this iteration.
- All aggregates respect the active `period` / `platform` / `org_ids` / `company_id` filters and reconcile to the underlying reviews (SC-002).

## Errors

| Status | When |
|--------|------|
| 401 | Unauthenticated |
| 422 | Invalid `period`/`platform` value or malformed UUID |
