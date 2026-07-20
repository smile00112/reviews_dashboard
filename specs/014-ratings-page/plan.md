# Implementation Plan: Ratings Page

**Branch**: `014-ratings-page` (dir: `specs/014-ratings-page`) | **Date**: 2026-07-20 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/014-ratings-page/spec.md`

## Summary

Add a read-only **Ratings** dashboard page (`/ratings`) that renders the prototype's `screen-rating`: a per-platform rating-distribution table, two monthly trend blocks (average rating, review volume), a weekly response-speed block (median/p95 vs a fixed SLA), and a Mon–Sun weekday breakdown with a best/worst-day insight. It reuses the overview feature's filter model (period + platform + org/company), its `DashboardService` helpers (`_selected_orgs`, `_scoped_filters`, `_published_expr`, `_response_delay_expr`, snapshot history), and its no-charting-library frontend convention (hand-rolled SVG/CSS). One new endpoint `GET /api/dashboard/ratings` backed by a new `DashboardService.ratings(...)` method; one new page reusing `DashboardFilters`; hand-rolled chart components.

## Technical Context

**Language/Version**: Python 3.13 (api), TypeScript / Next.js 15 App Router (web)

**Primary Dependencies**: FastAPI, SQLAlchemy 2.x, Pydantic v2 (api); Next.js, React (web). **No new dependency** — charts are hand-rolled SVG/CSS, matching feature 009/012.

**Storage**: PostgreSQL 16 (prod) / SQLite (tests) via the existing `Review`, `Organization`, `RatingSnapshot` models. No schema change (read-only over existing tables + feature-009 `rating_snapshot`).

**Testing**: pytest (api, `tests/conftest.py` SQLite), Playwright E2E (web).

**Target Platform**: Linux server (Docker Compose); internal browser dashboard.

**Project Type**: Web application (`apps/api` + `apps/web` monorepo).

**Performance Goals**: Page renders < 1 s at current volume (tens of orgs, ~50k reviews). Query count MUST NOT scale with review volume — bounded aggregate scans only, mirroring feature 012's `test_query_counts` discipline.

**Constraints**: Read-only (no writes, no scraping). Per-review data exists for the collected platforms (Yandex + 2ГИС); Google has no collector and contributes an aggregate rating + count only → «нет данных» placeholders. Reviews carry a calendar `review_date` but no posting time → weekday-only breakdown, no hour-of-day.

**Scale/Scope**: 1 endpoint, 1 service method (+ private helpers), 1 Pydantic schema module, 1 web page, ~5 web components, 1 nav entry, 1 api test module, E2E smoke.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. MVP Scope Discipline** — ✅ A read-only analytics view over already-collected reviews and existing platform aggregates. No excluded feature (no replies, no Google scraping, no LLM, no notifications). Adds no new provider or write path.
- **II. Read-Only Review Collection** — ✅ Page performs zero writes and triggers no scraping (FR-013).
- **III. Critical-Path Testing** — ✅ New aggregation logic (per-star distribution sums, weekday aggregation, response percentiles, filter scoping, empty-network) covered by `test_dashboard_ratings.py`; a query-count guard protects the volume-independence invariant. Dedup/normalization/scrape-persistence contracts are untouched.
- **IV. Scraper Reliability** — ✅ N/A; no scraper code touched.
- **V. Simplicity (YAGNI)** — ✅ One endpoint + one service method reusing existing helpers; no new table, no new dependency, no charting lib. Hour-of-day heatmap and SLA-config UI explicitly out of scope.
- **VI. Deterministic Local Analytics** — ✅ All figures are deterministic SQL aggregates over stored data; no external/LLM calls; degrades to empty states, never raises.
- **VII. Admin Panel Security** — ✅ Endpoint reuses the existing `get_current_user` auth dependency (same as `/api/dashboard/overview`); unauthenticated → 401. No new auth system.
- **VIII. Multi-Provider Collection** — ✅ N/A; no collection path added. Read side honors the existing per-platform data shape.

**Result: PASS. No violations → Complexity Tracking omitted.**

## Project Structure

### Documentation (this feature)

```text
specs/014-ratings-page/
├── plan.md              # This file
├── spec.md              # Feature spec
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   └── dashboard-ratings.md   # GET /api/dashboard/ratings contract
├── checklists/
│   └── requirements.md
└── tasks.md             # Phase 2 (/speckit-tasks — not created here)
```

### Source Code (repository root)

```text
apps/api/app/
├── services/dashboard_service.py   # + ratings(...) method & private helpers (rating trend,
│                                    #   volume trend, weekday stats, per-star distribution,
│                                    #   weekly response percentiles)
├── schemas/dashboard.py            # + DashboardRatings + nested models
└── api/dashboard.py                # + GET /api/dashboard/ratings router

apps/api/tests/
└── test_dashboard_ratings.py       # new critical-path tests (+ query-count guard)

apps/web/
├── app/(dashboard)/ratings/page.tsx           # new page (client component, URL-driven filters)
├── components/dashboard/ratings/
│   ├── platform-distribution-table.tsx
│   ├── rating-trend-chart.tsx                  # SVG multi-line
│   ├── volume-trend-chart.tsx                  # SVG/CSS stacked bars
│   ├── response-speed-chart.tsx                # SVG lines + dashed SLA
│   └── weekday-breakdown.tsx                   # CSS bar row, color by avg rating
├── components/shell/sidebar.tsx                # + «Рейтинги» nav item
├── lib/api.ts                                  # + getDashboardRatings(params)
└── lib/types.ts                                # + DashboardRatings + nested types

apps/web/tests/
└── ratings.spec.ts                             # E2E smoke (page renders, filter changes URL)
```

**Structure Decision**: Web application monorepo (Option 2). This feature is purely additive to the existing `apps/api` (services/schemas/api layers) and `apps/web` (App Router page + components), following the feature 009/012/013 dashboard pattern exactly. No new top-level modules.

## Phase 0 — Research

See [research.md](./research.md). Resolves: monthly bucketing of snapshots for the two trend blocks, weekly bucketing + percentile computation for response speed (Postgres `percentile_cont` vs SQLite fallback), weekday extraction across dialects, per-star distribution query shape, and the «нет данных» contract for Google/2ГИС.

## Phase 1 — Design & Contracts

- [data-model.md](./data-model.md) — entities consumed (Review, Organization aggregates, RatingSnapshot) and the composed `DashboardRatings` payload shape; no persistence changes.
- [contracts/dashboard-ratings.md](./contracts/dashboard-ratings.md) — request params, response schema, status codes, error cases.
- [quickstart.md](./quickstart.md) — how to run and validate the feature end to end.

**Post-design Constitution re-check: PASS** (no new violations introduced by the design; still one endpoint, one method, no schema change, no new dependency).
