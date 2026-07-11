# Implementation Plan: Network Overview Dashboard

**Branch**: `009-network-overview` | **Date**: 2026-07-11 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/009-network-overview/spec.md`

## Summary

Read-only network-level analytics landing page ("Обзор") aggregating review data across all organization branches, filterable by period / platform / organization. Adds one backend aggregation endpoint (`GET /api/dashboard/overview`) backed by a new `DashboardService`, and a new daily `rating_snapshot` table (migration 0012) captured on scrape success to enable period-over-period rating deltas. Frontend adds a Next.js App Router overview page (dashboard home) with hand-rolled SVG donuts + CSS bars, no new npm dependency. Reuses existing deterministic local analytics (`analysis/analyzer.summarize`), the existing auth/RBAC, and leaves the review dedup contract frozen.

## Technical Context

**Language/Version**: Python 3.11 (FastAPI backend); TypeScript 5.7 / Node (Next.js 15, React 19) frontend.

**Primary Dependencies**: FastAPI, SQLAlchemy, Alembic, Pydantic (backend); Next.js App Router, Tailwind (frontend). No new runtime dependency — charts are hand-rolled SVG.

**Storage**: PostgreSQL 16 (SQLite for backend tests via `JSON().with_variant`). New table `rating_snapshot`.

**Testing**: pytest (backend aggregation + snapshot idempotency); Playwright (frontend overview e2e).

**Target Platform**: Docker Compose stack — web :3000, api :8000.

**Project Type**: Web application (monorepo `apps/api` + `apps/web`).

**Performance Goals**: Overview response < 2s for tens of organizations; page recompute on filter change < 2s (SC-003).

**Constraints**: Read-only; deterministic local analytics only (no LLM/external); no new charting dependency; dedup contract (`build_review_hash`, `uq_review_org_hash`) unchanged; Google is display-only of stored aggregates (no scraping).

**Scale/Scope**: Internal tool, ~tens of organizations, small operator team. One new page, one endpoint, one table.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. MVP Scope Discipline | ✅ | Analytics over already-collected reviews; a dashboard view of existing data. No excluded feature introduced. |
| II. Read-Only Review Collection | ✅ | FR-018: strictly read-only; no reply/edit/delete. Google figures are display-only of operator-entered aggregates — **no Google collection** introduced (constitution keeps Google excluded as a *provider*). |
| III. Critical-Path Testing | ✅ | New logic (aggregation, snapshot capture) gets pytest coverage; dedup/normalization untouched. |
| IV. Scraper Reliability | ✅ | Snapshot capture hooks the *success* path of existing scrape flow additively; does not alter run records or failure artifacts. |
| V. Simplicity (YAGNI) | ✅ | One service, one endpoint, one additive table, background-task-free. No new dependency (SVG charts). No queue. |
| VI. Deterministic Local Analytics | ✅ | Reuses `analysis/analyzer.summarize`; no external inference. |
| VII. Admin Panel Security | ✅ | Endpoint guarded by existing auth dependency; reuses users/roles/session; no second auth. Read-only for both roles. |
| VIII. Multi-Provider Collection | ✅ | No new provider/scraper. Snapshot reads existing per-platform columns. |

**Result**: PASS. No violations → Complexity Tracking empty.

## Project Structure

### Documentation (this feature)

```text
specs/009-network-overview/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   └── dashboard-overview.md   # GET /api/dashboard/overview contract
└── tasks.md             # Phase 2 (/speckit-tasks)
```

### Source Code (repository root)

```text
apps/api/
├── alembic/versions/
│   └── 0012_rating_snapshot.py           # new table
├── app/
│   ├── models/
│   │   └── rating_snapshot.py            # new ORM model
│   ├── schemas/
│   │   └── dashboard.py                  # new Pydantic response models
│   ├── services/
│   │   ├── dashboard_service.py          # new aggregation service
│   │   └── scrape_service.py             # +snapshot capture on success
│   ├── analysis/
│   │   └── analyzer.py                   # summarize() reused (generalize input if needed)
│   ├── api/
│   │   └── dashboard.py                  # new router
│   └── main.py                           # register dashboard router
└── tests/
    ├── test_dashboard_overview.py        # aggregation contract
    └── test_rating_snapshot.py           # snapshot idempotency + delta

apps/web/
├── app/(dashboard)/
│   └── page.tsx                          # overview = dashboard home (server component)
├── components/dashboard/
│   ├── kpi-hero.tsx
│   ├── kpi-strip.tsx
│   ├── rating-distribution.tsx
│   ├── sentiment-donut.tsx               # client, SVG
│   ├── platform-donut.tsx               # client, SVG
│   ├── platform-cards.tsx
│   ├── attention-list.tsx
│   ├── worst-locations-table.tsx
│   ├── trending-aspects-table.tsx
│   └── dashboard-filters.tsx             # client, pushes to searchParams
├── lib/
│   ├── types.ts                          # +DashboardOverview types
│   └── api.ts                            # +getDashboardOverview()
└── tests-e2e/
    └── dashboard.spec.ts                 # overview e2e
```

**Structure Decision**: Existing monorepo web-application layout (`apps/api` FastAPI + `apps/web` Next.js). Feature is additive: new files plus a single additive edit each to `scrape_service.py` (capture hook) and `main.py` (router registration). No existing route, model, or the dedup path is modified.

## Complexity Tracking

> No constitution violations. Table intentionally empty.
