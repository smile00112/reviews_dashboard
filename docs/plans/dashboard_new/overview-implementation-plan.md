# Implementation Plan — Dashboard "Обзор" (screen-overview)

> **Status (2026-07-11): SHIPPED.** Delivered via Spec Kit feature `specs/009-network-overview/`
> (spec → plan → tasks → implement). All prototype blocks implemented (US1–US5): endpoint
> `GET /api/dashboard/overview`, `rating_snapshot` history (migration 0012), page at `/overview`.
> Backend 191 tests pass; web build + lint + tsc clean. E2E `apps/web/tests/overview.spec.ts`
> (smokes run headless; full render suite gated on `E2E_ADMIN_EMAIL`/`E2E_ADMIN_PASSWORD` + live stack).
> This document is the original analysis; `specs/009-network-overview/` is the source of truth.


Source prototype: `docs/plans/dashboard_new/GeoMonitor — SERM Dashboard Prototype.html` (lines 1532–1830).
Target: first page of new dashboard = network overview.

## Decisions (locked)

1. **Rating deltas** → new `rating_snapshot` table (migration 0012) + daily capture. Deltas empty until history accrues.
2. **Out-of-scope blocks** (competitors "vs рынок", per-review negativity/response-speed for Google/2ГИС) → render with `нет данных` placeholder, keep layout.
3. **Scope** → whole network (global) **plus** filters by organization(s). Company filter reuses `company_id`.
4. **Charts** → hand-rolled SVG (2 donuts) + CSS bars. No new npm dependency.

## Data availability summary

Ready now (no new data): header counts, review-count KPIs, unanswered KPIs, rating distribution, sentiment donut, reputation index, positivity %, worst-locations (rating + unanswered), trending aspects (from `problems` JSONB + `review_date`), attention feed (unanswered/negative/escalated), platform review counts.

Blocked → handled by decisions: all `Δ`/падение deltas (→ snapshot table), SLA % (→ constant threshold const), response-time metrics (→ `response_first_seen_at` proxy, labelled approximate), Google/2ГИС per-review (→ `нет данных`).

## Backend

### 1. Migration `0012_rating_snapshot`
```
rating_snapshot(
  id uuid pk,
  organization_id uuid fk -> organizations,
  platform enum(yandex|google|gis2),
  rating numeric(3,2),
  review_count int,
  captured_on date,             -- one row per org/platform/day
  captured_at timestamptz,
  unique(organization_id, platform, captured_on)
)
```
Index on `(organization_id, captured_on)`.

### 2. Snapshot capture
- Hook into `ScrapeService.execute_run` success path: upsert today's snapshot for the scraped platform (Yandex from `org.rating/review_count`; 2ГИС/Google from `gis2_*`/`google_*` when operator edits them).
- Idempotent per day (unique constraint → upsert).
- Optional backfill: seed one snapshot per org today so deltas start from a baseline.

### 3. `DashboardService` (new, `services/dashboard_service.py`)
One method: `overview(period, platform, org_ids | company_id) -> dict`. Aggregates across selected orgs:
- **kpi_hero**: avg network rating (weighted by review_count) + snapshot delta; new-in-period / today / total / per-day-avg counts; unanswered total + 24h delta + overdue(>24h) count.
- **kpi_strip**: avg/median/p95 response time (from `response_first_seen_at − first_seen_at`), SLA% (const threshold), positivity% (sentiment), reputation index (5★ − 1–3★ share).
- **rating_distribution**: counts per star 1–5 + 4–5★ / 1–3★ shares.
- **sentiment_distribution**: pos/neu/neg (reuse `analyzer.summarize` logic, generalized across orgs).
- **platform_breakdown**: review counts per platform (Yandex reviews + `org.*_review_count`), per-platform weighted rating + snapshot delta; negativity/response-speed only where data exists else null.
- **attention[]**: unanswered>24h, new negatives(≤2★, short window), escalated (`status`), rating-drop points (snapshot delta < threshold), aspect-growth (windowed `problems` compare).
- **worst_locations[]**: per-org rating + monthly snapshot delta + unanswered count, sorted asc, top 10.
- **trending_aspects[]**: `problems` category counts 7d vs prev 7d + sentiment split.

Reuse existing `analyzer.summarize` for sentiment/problem aggregation; extend to multi-org input.

### 4. Schema + endpoint
- `schemas/dashboard.py`: `DashboardOverview` Pydantic model mirroring the dict.
- `api/dashboard.py`: `GET /api/dashboard/overview` with query params `period` (day|week|30d|90d|year|all), `platform` (all|yandex|google|gis2), `org_ids` (repeatable) or `company_id`. Thin router → `DashboardService`.
- Register router in `app/main.py`.

### 5. Tests
- `test_dashboard_overview.py`: KPI counts, distribution sums, unanswered logic, empty-network zeroed summary, org filter narrows result.
- `test_rating_snapshot.py`: upsert idempotency per day, delta computation.

## Frontend

### 1. Types + API
- `lib/types.ts`: `DashboardOverview` + nested types mirroring schema.
- `lib/api.ts`: `getDashboardOverview(params)`.

### 2. Page
- Make overview the dashboard home → `app/(dashboard)/page.tsx` (or `app/(dashboard)/overview/page.tsx` + redirect). Server component, fetches overview, reads filters from `searchParams`.

### 3. Components (`components/dashboard/`)
- `kpi-hero.tsx` — 3 big KPI cards (rating / new / unanswered) with delta + bench line.
- `kpi-strip.tsx` — 5 mini KPIs.
- `rating-distribution.tsx` — CSS horizontal bars (port prototype markup).
- `sentiment-donut.tsx`, `platform-donut.tsx` — hand-rolled SVG donut + legend (client components).
- `platform-cards.tsx` — 3 platform aggregate cards; `нет данных` where null.
- `attention-list.tsx` — attention feed, each row links to `/reviews` or `/organizations/[id]`.
- `worst-locations-table.tsx`, `trending-aspects-table.tsx`.
- `dashboard-filters.tsx` (client) — period chips + platform chips + org/company multiselect; pushes to `searchParams`.

Port CSS tokens from prototype `:root` into Tailwind config / a scoped stylesheet (dark theme: `--bg #0f1117`, `--accent #d4ff3a`, etc.).

### 4. E2E
- `dashboard.spec.ts`: page renders, KPIs present, filter changes URL + refetches.

## Build order

1. Migration 0012 + snapshot capture + tests.
2. `DashboardService` + schema + endpoint + tests (verify with real DB).
3. Frontend types/api + page + components.
4. Filters (period/platform/org).
5. E2E + lint gate.

## Out of scope this page

Competitors data, SLA config UI, Google/2ГИС review scraping, real-time push. Deltas display empty until snapshot history accrues (~30 days for month deltas).
