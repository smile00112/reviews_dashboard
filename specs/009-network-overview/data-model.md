# Phase 1 Data Model: Network Overview Dashboard

Only one new persisted entity. Everything else is read from existing tables (`organizations`, `reviews`, `companies`) and computed on read.

## New entity: `rating_snapshot`

Daily point-in-time capture of an organization's rating per platform, enabling period-over-period deltas.

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | default uuid4 |
| `organization_id` | UUID FK → organizations(id) ON DELETE CASCADE | indexed |
| `platform` | enum(`yandex`,`google`,`gis2`) | reuse `ReviewPlatform` / `review_platform_enum` |
| `rating` | Numeric(3,2) nullable | platform rating at capture time |
| `review_count` | Integer nullable | platform review count at capture time |
| `captured_on` | Date | day bucket (server date) |
| `captured_at` | timestamptz | exact capture instant, `server_default now()` |

**Constraints / indexes**:
- `UNIQUE (organization_id, platform, captured_on)` — one row per org/platform/day (enables idempotent upsert).
- Index `(organization_id, captured_on)` for delta lookups.

**Lifecycle**:
- Written by `DashboardService.capture_snapshot(org, platform)` invoked from `ScrapeService.execute_run` success path, and optionally a manual/backfill call.
- Upsert on the unique key: same-day re-scrape overwrites the day's snapshot (latest value wins).
- Never updated after its day rolls over (historical).
- Never participates in review dedup.

**Delta computation**: for a requested period, `delta = current_org_rating − rating_snapshot.rating` where snapshot is the earliest row with `captured_on >= period_start` (fallback: nearest ≤ period_start). If no snapshot in range → delta is `null` → UI renders "—".

## Existing entities (read-only inputs)

### Organization (branch)
Used fields: `id`, `name`, `city`, `region`, `is_franchise`, `company_id`, `rating`, `review_count`, `yandex_rating_count`, `gis2_rating`, `gis2_review_count`, `google_rating`, `google_review_count`.

### Review
Used fields: `organization_id`, `rating` (1–5), `review_date`, `first_seen_at`, `response_text` (NULL ⇒ unanswered), `response_first_seen_at` (response-time proxy), `status` (`new`/`in_progress`/`answered`/`escalated`), `platform`, `sentiment`, `problems` (JSONB list of `{category, ...}`), `analyzed_at`.

### Company
Used fields: `id`, `name` — optional filter scope for organizations.

## Derived (non-persisted) shapes

Computed by `DashboardService.overview(...)` and returned via `schemas/dashboard.py`:

- **KPI hero**: `network_avg_rating` (+ `delta`), `new_in_period`, `new_today`, `total_reviews`, `avg_per_day`, `unanswered_total`, `unanswered_delta_24h`, `overdue_24h`.
- **KPI strip**: `response_avg_min`, `response_median_min`, `response_p95_min`, `sla_percent`, `positivity_percent`, `reputation_index`. Response-time fields carry an `approximate: true` flag.
- **rating_distribution**: `[{star:1..5, count, percent}]` + `share_4_5`, `share_1_3`.
- **sentiment**: `{positive, neutral, negative}` counts + percents (from `summarize`).
- **platform_breakdown**: `[{platform, review_count}]`.
- **platform_cards**: `[{platform, weighted_rating, rating_delta|null, negativity_percent|null, response_speed_hours|null}]` — `null` ⇒ "нет данных".
- **attention[]**: `[{type, title, subtitle, count|value, severity, link}]` (types: `unanswered_overdue`, `fresh_negative`, `escalated`, `rating_drop`, `aspect_spike`).
- **worst_locations[]**: `[{organization_id, city, name, rating, rating_delta|null, unanswered_count}]` (≤10, rating asc).
- **trending_aspects[]**: `[{category, mentions, change_percent, sentiment:{pos,neu,neg}}]`.

All derived numbers reconcile to the underlying reviews for the active filters (SC-002).
