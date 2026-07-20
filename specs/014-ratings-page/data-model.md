# Phase 1 Data Model: Ratings Page

**No persistence changes.** This feature is read-only over existing tables. No migration, no new column, no ORM change. The "model" here is the composed response payload.

## Existing entities consumed

### Review (`apps/api/app/models/review.py`)
| Field | Use in this feature |
|---|---|
| `organization_id` | org/company scoping |
| `platform` | per-platform split (Yandex + 2ГИС have rows; Google has none) |
| `rating` (1–5) | per-star distribution, weekday average rating |
| `review_date` (Date, nullable) | period membership (via `_published_expr`), weekday breakdown |
| `first_seen_at` | response-delay basis, `_published_expr` fallback |
| `response_first_seen_at` | response-delay basis (answered rows only) |
| `removed_at` (nullable) | active vs removed split — active only in distribution shares; removed counted separately |

### Organization (`apps/api/app/models/organization.py`)
| Field | Use |
|---|---|
| `company_id` | company filter |
| `rating` / `review_count` | Yandex aggregate |
| `google_rating` / `google_review_count` | Google aggregate row (no collector -> per-star unavailable) |
| `gis2_rating` / `gis2_review_count` | 2ГИС aggregate (per-star comes from its review rows) |

### RatingSnapshot (`apps/api/app/models/rating_snapshot.py`, feature 009)
| Field | Use |
|---|---|
| `organization_id`, `platform` | scoping / series split |
| `rating`, `review_count` | monthly dynamics + volume series values |
| `captured_on` (date, unique per org+platform+day) | month bucketing |

## Composed payload: `DashboardRatings`

Returned by `GET /api/dashboard/ratings`. All `null` values mean "no data" and MUST render as «нет данных» / an empty state — never as `0`.

```text
DashboardRatings
├── period: str                     # echo of the request period
├── platform: str                   # echo of the request platform
├── generated_at: datetime
├── platform_distribution: PlatformDistributionRow[]
├── rating_trend: TrendBlock         # monthly average rating per platform
├── volume_trend: TrendBlock         # monthly review count per platform
├── response_speed: ResponseSpeedBlock
└── weekday: WeekdayBlock
```

### PlatformDistributionRow
| Field | Type | Notes |
|---|---|---|
| `platform` | `str` | `yandex` \| `google` \| `gis2` |
| `label` | `str` | «Яндекс Бизнес» / «Google Business» / «2ГИС» |
| `avg_rating` | `float \| null` | weighted aggregate across selected orgs |
| `total_reviews` | `int \| null` | active reviews (Yandex) or aggregate count |
| `stars` | `StarShare[] \| null` | `null` ⇒ «нет данных» (Google only) |
| `removed_count` | `int \| null` | `null` ⇒ «нет данных» (Google only) |

**StarShare**: `{ star: 1..5, count: int, share: float }` — `share` is a percentage of active reviews; the five `count`s sum to `total_reviews` (SC-002).

### TrendBlock
| Field | Type | Notes |
|---|---|---|
| `labels` | `str[]` | ordered month keys, e.g. `"2026-03"` |
| `series` | `TrendSeries[]` | one per platform |

**TrendSeries**: `{ platform: str, label: str, color: str, points: (float \| null)[] }` — `points` aligns index-wise with `labels`; `null` = no snapshot that month (gap, not zero). Empty `labels` ⇒ "history accruing" empty state.

### ResponseSpeedBlock
| Field | Type | Notes |
|---|---|---|
| `labels` | `str[]` | ordered ISO week keys |
| `median_minutes` | `(float \| null)[]` | index-aligned with `labels` |
| `p95_minutes` | `(float \| null)[]` | index-aligned |
| `sla_target_minutes` | `int` | constant from settings (same source as overview) |

Empty `labels` ⇒ empty state (no answered reviews in scope).

### WeekdayBlock
| Field | Type | Notes |
|---|---|---|
| `days` | `WeekdayStat[]` | exactly 7, ordered Mon→Sun |
| `insight` | `str \| null` | best/worst weekday sentence; `null` when fewer than 2 days carry data |

**WeekdayStat**: `{ weekday: 0..6 (0=Mon), label: "Пн".."Вс", count: int, avg_rating: float | null }` — `count` may be `0` (a real zero: that weekday genuinely had no reviews); `avg_rating` is `null` when `count == 0`.

## Validation rules (from requirements)

- Per-star `count`s sum to the platform's active review total (FR-003, SC-002).
- Removed reviews are excluded from `stars` shares and counted only in `removed_count` (FR-003).
- The Google row carries `stars = null` and `removed_count = null` (FR-004).
- Every block honors period + platform + org/company scope identically (FR-010).
- Any block lacking data returns an empty collection or `null` fields, never an error (FR-011).
- The weekday block ignores reviews with `review_date IS NULL` (edge case) but they still count in `platform_distribution`.
