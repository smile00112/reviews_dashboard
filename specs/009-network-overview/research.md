# Phase 0 Research: Network Overview Dashboard

All open questions were pre-decided in `docs/plans/dashboard_new/overview-implementation-plan.md` and the spec's Assumptions. Consolidated below.

## R1 — Period-over-period rating deltas

**Decision**: New daily `rating_snapshot` table (org × platform × day) capturing rating + review_count. Deltas computed as `current − snapshot at (period start)`.

**Rationale**: Ratings are stored as a single current scalar on `organizations`; no history exists. A snapshot table is the minimal additive way to get trustworthy deltas. Capture piggybacks the existing scrape-success path (no scheduler, no Celery — Principle V).

**Alternatives considered**:
- Compute windowed average from `review_date` — rejected: noisy, depends on review dates that are often coarse/missing, and does not reflect the platform's own displayed rating.
- TimescaleDB / dedicated time-series — rejected: explicitly out of scope (constitution).

**Consequence**: Deltas are empty until history accrues (~30 days for month deltas). Spec FR-015 / SC-004 encode this.

## R2 — Response-time metrics

**Decision**: Derive from `reviews.response_first_seen_at − reviews.first_seen_at`; label all response-time KPIs "approximate".

**Rationale**: `response_first_seen_at` is an observation-time proxy (feature 007) set when a response first appears during scraping. No exact provider reply timestamp exists. Granularity = scrape interval.

**Alternatives**: Fetch exact reply time — not available read-only. Omit metric — rejected, prototype shows it and the proxy is directionally useful.

## R3 — "Answered within SLA" share

**Decision**: Fixed constant threshold (24h) in settings. SLA% = share of answered reviews whose approximate response time ≤ threshold.

**Rationale**: No per-organization SLA config exists; a constant is the YAGNI choice for this iteration. Configurable SLA is a future enhancement.

## R4 — Missing / unavailable data (competitors, Google/2GIS per-review)

**Decision**: Render explicit "нет данных" placeholder; never fabricate or zero-fill.

**Rationale**: Competitor benchmark has no data source; Google/2GIS have only operator-entered aggregate rating/review_count columns, no per-review rows, so per-review-derived metrics (negativity, response speed, sentiment) cannot be computed for them. SC-005 requires an unambiguous placeholder so a zero is never misread as real.

## R5 — Google display vs constitution exclusion

**Decision**: Show Google's aggregate rating/review_count where the operator has entered them; everything per-review = "нет данных". Introduce **no** Google scraping.

**Rationale**: Constitution excludes Google as a *collection* provider. The `google_*` columns already exist (migration 0010, additive, operator-editable). Displaying already-stored values is read-only display, not collection. Plan Constitution Check confirms this stays within Principle II.

## R6 — Charting

**Decision**: Hand-rolled inline SVG for the two donuts; CSS flex bars for the star distribution (as in the prototype). No charting library.

**Rationale**: Only two donuts and one bar list; a dependency (Chart.js/Recharts) is unjustified weight (Principle V). SVG donut = two `stroke-dasharray` arcs. Client components only where interactivity/measurement is needed.

## R7 — Aggregation reuse

**Decision**: Reuse `analysis/analyzer.summarize(rows)` for sentiment + problem-category aggregation, feeding it the union of reviews across selected organizations. `DashboardService` maps ORM rows → the dict shape `summarize` expects, exactly as `AnalysisService.summary` does per-org.

**Rationale**: Keeps analytics deterministic and single-sourced (Principle VI); avoids duplicating sentiment math.

## R8 — Filtering model

**Decision**: Endpoint query params `period` (day|week|30d|90d|year|all), `platform` (all|yandex|google|gis2), and repeatable `org_ids` (UUID) optionally scoped by `company_id`. Frontend stores filter state in URL `searchParams`; server component refetches.

**Rationale**: Stateless, shareable URLs, matches existing `apps/web` server-component + `lib/api.ts` pattern. No client store needed.

## Open questions

None. All NEEDS CLARIFICATION resolved.
