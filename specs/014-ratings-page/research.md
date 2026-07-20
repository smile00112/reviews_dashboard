# Phase 0 Research: Ratings Page

All decisions reuse existing feature-009/012/013 machinery in `DashboardService`. No new dependencies.

## 1. Per-star distribution table (block 1)

**Decision**: For the collected platforms (**Yandex and 2ГИС** — both have collectors per Constitution Principle VIII), one grouped scan `GROUP BY (platform, rating)` over reviews scoped by org/period gives the 5→1 counts; shares are `count/total*100` computed in Python, over active (`removed_at IS NULL`) rows only. `removed_count` is a conditional count (`removed_at IS NOT NULL`) in the same scan via `func.count(case(...))`. `avg_rating` for those platforms is weighted from the same counts, so the average and the star shares always agree. **Google** has no collector, so it reads `Organization.google_rating` weighted by `google_review_count`.

> **Corrected during implementation.** The initial analysis assumed Yandex was the only per-review platform. Verifying against the real database showed 2ГИС holds 71 039 review rows (feature 006 collects them via the 2GIS reviews API), so `_PER_REVIEW_PLATFORMS = {yandex, gis2}` and Google is the sole aggregate-only platform.

**Rationale**: A single `GROUP BY rating` scan keeps query count constant. Reusing `_scoped_filters` + `_published_expr` keeps period semantics identical to the overview. Active-only shares match the removal-tracking contract (feature 011): removed reviews are excluded from default aggregates.

**Alternatives considered**: Reusing the overview `_review_cube` (grouped by platform×rating×sentiment) — rejected because it is already period-windowed for the overview's needs and does not carry the removed/active split cleanly for a distribution table; a purpose-built small scan is clearer and equally cheap.

**Google «нет данных»**: its per-star and removed fields are `null` in the payload (never `0`), so the frontend renders «нет данных» rather than a misleading zero (FR-004, FR-011).

## 2. Rating dynamics & review volume trends (blocks 2, 3)

**Decision**: Bucket `RatingSnapshot` rows by calendar month (`captured_on`) and platform. For each (month, platform) take the **latest** snapshot in that month: its `rating` feeds the dynamics line, its `review_count` feeds the volume bars. Bound the month range by the selected period (`period` → number of months; `all`/`custom` → span of available snapshots or the custom range). Assemble ordered month labels + one series per platform.

**Rationale**: Snapshots are daily and idempotent per org/platform/day (unique constraint, feature 009). Month granularity matches the prototype (12 months). "Latest snapshot in month" is a stable month-end reading and avoids averaging noise. Network figures aggregate across the selected orgs: dynamics = review-count-weighted average rating per month; volume = sum of review counts per month.

**Sparse history**: only months that have snapshots appear; no fabrication (FR-005, edge case). With no history, blocks return empty series and the UI shows a "data accruing" state.

**Cross-dialect month key**: Postgres `date_trunc('month', captured_on)` / `to_char`; SQLite `strftime('%Y-%m', captured_on)`. Follow the existing `self.db.get_bind().dialect.name == "sqlite"` branch pattern already used throughout the service.

**Alternatives considered**: Deriving volume from live `Review` counts per month by `first_seen_at` — rejected: a bulk import stamps the whole backlog with one month, distorting the trend (the same reason `_published_expr` exists). Snapshots are the honest volume-over-time source.

## 3. Response speed weekly median/p95 (block 4)

**Decision**: Reuse `_response_delay_expr()` (seconds, dialect-aware). Bucket answered reviews by ISO week within the period, and per week compute median + p95. Postgres: `percentile_cont(0.5|0.95) WITHIN GROUP (ORDER BY delay) GROUP BY week`. SQLite: load per-week delays and use `statistics.median` + the existing `_percentile` helper (same approach as `_response_percentiles`, just grouped by week). Covers whichever collected platforms are in scope; platforms with no answered reviews contribute nothing and an empty scope yields an empty series. SLA target is the constant from `SettingsService.sla_threshold_minutes()` (same source as the overview), returned as a flat line value.

**Rationale**: Directly extends the proven `_response_percentiles` logic to a weekly grouping. No new delay math. Keeps a single grouped query on Postgres; SQLite fallback is test-only and small.

**Week key**: Postgres `date_trunc('week', published)`; SQLite `strftime('%Y-%W', published)`. Weeks ordered ascending, labeled by ISO week.

**Alternatives considered**: Averaging response time per week — rejected: the prototype and the overview both emphasize median/p95 precisely because a fat tail makes the mean misleading ("сильный хвост ≠ плохое среднее").

## 4. Weekday breakdown (block 5)

**Decision**: `GROUP BY weekday(review_date)` over scoped active reviews (all collected platforms), producing per-weekday `count` and `avg(rating)`. Weekday index: Postgres `extract(dow from review_date)` (0=Sun..6=Sat) or `extract(isodow ...)` (1=Mon..7=Sun); SQLite `strftime('%w', review_date)` (0=Sun..6=Sat). Normalize to Mon–Sun order in Python. The `insight` string names the lowest-avg-rating weekday ("пик жалоб") and the highest-avg-rating weekday ("лучшие оценки"), computed in Python from the seven rows.

**Rationale**: `review_date` is the only real temporal signal (posting date). Hour-of-day is unavailable (no posting time; `first_seen_at` is scrape time) → the prototype's 7×6 hour grid is reduced to a 7-row weekday breakdown (FR-009, locked in brainstorming). Reviews without a parsed `review_date` are simply excluded from this block only (edge case).

**Alternatives considered**: Using `first_seen_at` weekday — rejected: reflects when the scraper ran, not when customers posted; would be a meaningless axis.

## 5. Filters, period semantics, auth, payload contract

**Decision**: Mirror `overview` exactly — `period` ∈ `PERIOD_DAYS` keys (`day|week|30d|90d|year|all|custom`), `platform` ∈ `{all,yandex,google,gis2}`, `org_ids` (repeatable) or `company_id`, plus `date_from`/`date_to` for `custom`. Same 422 validation (invalid period/platform, custom without both bounds, `date_from > date_to`). Same `get_current_user` auth. Same `scope = None` optimization (drop the IN clause when the whole network is selected). Empty selection → fully-zeroed/empty payload (never 500).

**Rationale**: Consistency with the overview is a spec requirement (FR-001, FR-010, FR-012). Reusing the constants and validation avoids drift; the web `DashboardFilters` component already emits exactly these params.

**Frontend**: `/ratings` is a **client** component (the overview page is `"use client"` with `useSearchParams` + `useState`, not a server component — follow the actual current pattern, not the stale overview-plan doc). It reuses `DashboardFilters` and adds hand-rolled SVG/CSS chart components. Nav entry added to `components/shell/sidebar.tsx` (in the "Обзор" group).

## Open questions

None. All data-availability decisions were locked during brainstorming (heatmap → weekday-only; Google/2ГИС per-review → «нет данных»; full Spec Kit process).
