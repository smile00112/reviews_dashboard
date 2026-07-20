# Contract: `GET /api/dashboard/ratings`

Read-only comparative rating analytics for the Ratings page. Mirrors `GET /api/dashboard/overview` (feature 009/013) in auth, params, and validation.

## Request

`GET /api/dashboard/ratings`

**Auth**: required — `get_current_user` dependency (session cookie). Unauthenticated → `401`.

| Param | Type | Default | Notes |
|---|---|---|---|
| `period` | `day \| week \| 30d \| 90d \| year \| all \| custom` | `30d` | Must be a key of `PERIOD_DAYS`. |
| `platform` | `all \| yandex \| google \| gis2` | `all` | |
| `org_ids` | repeatable UUID | – | Organization filter. |
| `company_id` | UUID | – | Company (brand) filter; combines with `org_ids`. |
| `date_from` | date (`YYYY-MM-DD`) | – | Required with `period=custom`; ignored otherwise. |
| `date_to` | date (`YYYY-MM-DD`) | – | Required with `period=custom`; ignored otherwise. |

## Responses

### `200 OK` — `DashboardRatings`

```jsonc
{
  "period": "30d",
  "platform": "all",
  "generated_at": "2026-07-20T09:00:00Z",

  "platform_distribution": [
    {
      "platform": "yandex",
      "label": "Яндекс Бизнес",
      "avg_rating": 4.44,
      "total_reviews": 2070,
      "stars": [
        { "star": 5, "count": 1615, "share": 78.0 },
        { "star": 4, "count": 186,  "share": 9.0 },
        { "star": 3, "count": 62,   "share": 3.0 },
        { "star": 2, "count": 62,   "share": 3.0 },
        { "star": 1, "count": 145,  "share": 7.0 }
      ],
      "removed_count": 14
    },
    {
      "platform": "google",
      "label": "Google Business",
      "avg_rating": 4.51,
      "total_reviews": 4156,
      "stars": null,          // «нет данных» — Google has no collector
      "removed_count": null
    }
  ],

  "rating_trend": {
    "labels": ["2026-02", "2026-03", "2026-04"],
    "series": [
      { "platform": "yandex", "label": "Яндекс", "color": "#ffcc00", "points": [4.40, 4.42, 4.44] },
      { "platform": "gis2",   "label": "2ГИС",   "color": "#2ecc71", "points": [4.18, null, 4.16] }
    ]
  },

  "volume_trend": {
    "labels": ["2026-02", "2026-03", "2026-04"],
    "series": [
      { "platform": "yandex", "label": "Яндекс", "color": "#ffcc00", "points": [186, 189, 191] }
    ]
  },

  "response_speed": {
    "labels": ["2026-W12", "2026-W13"],
    "median_minutes": [14.0, 13.0],
    "p95_minutes": [255.0, 252.0],
    "sla_target_minutes": 120
  },

  "weekday": {
    "days": [
      { "weekday": 0, "label": "Пн", "count": 185, "avg_rating": 4.31 },
      { "weekday": 6, "label": "Вс", "count": 260, "avg_rating": 4.02 }
    ],
    "insight": "Пик жалоб — воскресенье (4.02). Лучшие оценки — понедельник (4.31)."
  }
}
```

**Null semantics** — `null` always means *no data available*, never zero:
- `stars` / `removed_count` = `null` → platform stores no per-review rows (Google).
- `avg_rating` = `null` → no rating known for that scope.
- A `points[i]` / `median_minutes[i]` = `null` → gap in that bucket (render as a line break, not a drop to zero).
- `weekday[].count` = `0` **is** real data (that day had no reviews); its `avg_rating` is then `null`.
- `insight` = `null` → fewer than two weekdays carry data.

### `401 Unauthorized`
No/invalid session.

### `422 Unprocessable Entity`
| Case | Detail |
|---|---|
| Unknown `period` | `Invalid period: {period}` |
| Unknown `platform` | `Invalid platform: {platform}` |
| `period=custom` missing a bound | `period=custom requires both date_from and date_to` |
| `date_from > date_to` | `date_from must not be after date_to` |

## Invariants

- **Read-only**: the endpoint performs no writes and triggers no scraping (FR-013).
- **Scope consistency**: every block reflects the same period/platform/org scope (FR-010).
- **Distribution integrity**: for a platform with `stars != null`, the five `count`s sum to `total_reviews`, counting active (non-removed) reviews only (SC-002).
- **Empty scope**: an org/company filter matching nothing returns `200` with empty/zeroed blocks, not an error (FR-011).
- **Query-count independence**: the number of SQL statements is constant — it grows with neither organization count nor review volume (feature 012 discipline).
