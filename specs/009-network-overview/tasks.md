# Tasks: Network Overview Dashboard

**Feature**: 009-network-overview | **Spec**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)

**Tests**: TDD requested for backend aggregation + `rating_snapshot` idempotency (pytest); Playwright e2e for the overview page.

**Paths**: backend `apps/api/…`, frontend `apps/web/…` (monorepo).

**Story priority**: US1 (P1) → US2, US3, US5 (P2) → US4 (P3).

**Progress**: Phase 1–3 (Setup + Foundational + US1 MVP) complete — 182 backend tests pass; web lint + typecheck clean. Overview shipped at route `/overview` (dashboard route group cannot own `/`; root `/` redirects to `/overview`).

---

## Phase 1: Setup

- [X] T001 Confirm current migration head: `alembic heads` → `0011_per_platform_scrape_status`; `0012_rating_snapshot` chains from it.
- [X] T002 [P] Add `overview_sla_threshold_minutes` (default 1440) setting to `apps/api/app/core/config.py` for the SLA% computation (research R3).

---

## Phase 2: Foundational (blocks all user stories)

**Purpose**: New table, capture hook, service+endpoint skeleton, and shared frontend plumbing that every block builds on.

### Data layer

- [X] T003 Create ORM model `RatingSnapshot` in `apps/api/app/models/rating_snapshot.py` (org_id FK, platform enum reuse `review_platform_enum`, rating, review_count, captured_on Date, captured_at; unique `(organization_id, platform, captured_on)`, index `(organization_id, captured_on)`). Register in `apps/api/app/models/__init__.py`.
- [X] T004 Write Alembic migration `apps/api/alembic/versions/0012_rating_snapshot.py` (down_revision `0011`) creating `rating_snapshot` with the unique constraint + index; downgrade drops the table.
- [X] T005 [P] [TDD] Write `apps/api/tests/test_rating_snapshot.py`: capture writes one row/day; same-day re-capture upserts; delta returns nearest snapshot >= period_start and `None` when history absent.
- [X] T006 Add `capture_snapshot` + `rating_delta` helpers to new `apps/api/app/services/dashboard_service.py`; T005 green.
- [X] T007 Additive edit `apps/api/app/services/scrape_service.py`: on run **success**, call `DashboardService(db).capture_snapshot(...)` for the scraped platform, wrapped so a snapshot error never fails the scrape (Principle IV).

### Service + endpoint skeleton

- [X] T008 In `dashboard_service.py` implement the shared query base: `period`→date window, `platform` filter, `org_ids`/`company_id` narrowing into a reusable filtered query.
- [X] T009 [P] Create `apps/api/app/schemas/dashboard.py` with `DashboardOverview` + nested sub-models per contracts; nullable delta/placeholder fields `float | None`.
- [X] T010 Create router `apps/api/app/api/dashboard.py` — `GET /api/dashboard/overview` (period/platform/org_ids/company_id), guarded by auth (401 unauth), 422 on invalid period/platform. Register in `apps/api/app/main.py`.
- [X] T011 [P] [TDD] `apps/api/tests/test_dashboard_overview.py` skeleton: empty network → 200 zeroed; unauth → 401; invalid period/platform → 422.
- [X] T012 Implement `DashboardService.overview(...)` returning full-shaped payload with zeroed/empty blocks so T011 passes.

### Frontend plumbing

- [X] T013 [P] Add `DashboardOverview` + nested TS types to `apps/web/lib/types.ts`.
- [X] T014 [P] Add `getDashboardOverview(params)` to `apps/web/lib/api.ts`.
- [X] T015 Create overview page `apps/web/app/(dashboard)/overview/page.tsx` (client component; reuses existing dark design tokens); root `/` (`app/page.tsx`) redirects to `/overview`; sidebar nav gains "Обзор сети".

**Checkpoint**: endpoint returns valid payload; page renders; snapshot capture works. ✅

---

## Phase 3: User Story 1 — Headline KPIs (P1) 🎯 MVP

**Goal**: Greeting header + 3 hero KPIs + 5 mini KPIs, network-aggregated for the default 30d/all view.

**Independent test**: Seed reviews across orgs; verify header counts, hero KPIs, and strip KPIs match aggregates; empty network shows zeros.

- [X] T016 [US1] [TDD] Extend `test_dashboard_overview.py`: hero KPIs + header counts reconcile to seeded data; org filter narrows.
- [X] T017 [US1] Implement header + `kpi_hero` in `DashboardService` (weighted avg from org rating×review_count; new/unanswered/overdue from filtered reviews). Green.
- [X] T018 [US1] Implement `kpi_strip`: response avg/median/p95 from `response_first_seen_at − first_seen_at` (approximate), SLA% vs threshold, positivity% (summarize), reputation_index. Green.
- [X] T019 [US1] [P] Build `apps/web/components/dashboard/kpi-hero.tsx` (3 cards, delta + bench; delta null → "—").
- [X] T020 [US1] [P] Build `apps/web/components/dashboard/kpi-strip.tsx` (5 mini KPIs; response-time "приблизительно").
- [X] T021 [US1] Render greeting header + period/platform chips + wire hero/strip into overview page.

**Checkpoint**: MVP — operator sees network pulse on landing. ✅

---

## Phase 4: User Story 2 — Distribution & sentiment (P2)

**Goal**: 1–5★ distribution, sentiment donut, platform review-count donut, 3 platform cards.

**Independent test**: mixed-rating/sentiment reviews → bars, donuts, and platform counts sum to totals; unavailable platform metrics show "нет данных".

- [X] T022 [US2] [TDD] Extend `test_dashboard_overview.py`: `rating_distribution`, `sentiment` (via summarize), `platform_breakdown`, `platform_cards` (null for uncomputable Google/2GIS per-review fields).
- [X] T023 [US2] Implement `rating_distribution` + `sentiment` in `DashboardService` (reuse `summarize` over multi-org rows).
- [X] T024 [US2] Implement `platform_breakdown` + `platform_cards` (Yandex from reviews; Google/2GIS aggregate rating from org columns, per-review fields → `None`; rating_delta from snapshots).
- [X] T025 [US2] [P] Build `apps/web/components/dashboard/rating-distribution.tsx` (CSS bars). Shared `panel.tsx` + `donut.tsx` helpers added.
- [X] T026 [US2] [P] Build `apps/web/components/dashboard/sentiment-donut.tsx` (client, SVG donut + legend).
- [X] T027 [US2] [P] Build `apps/web/components/dashboard/platform-donut.tsx` (client, SVG donut + legend).
- [X] T028 [US2] [P] Build `apps/web/components/dashboard/platform-cards.tsx` (3 cards; `null` → "нет данных").
- [X] T029 [US2] Wire the four US2 components into the overview page.

---

## Phase 5: User Story 3 — Attention feed (P2)

**Goal**: Prioritized 24h attention list (unanswered>24h, fresh negatives, escalated, rating drops, aspect spikes) with links.

**Independent test**: seed each attention condition → each surfaces with correct count, ordered by criticality; rating-drop omitted when no snapshot history.

- [X] T030 [US3] [TDD] Extend `test_dashboard_overview.py`: attention items for unanswered_overdue, fresh_negative, escalated, aspect_spike; rating_drop present only with snapshot history; severity ordering.
- [X] T031 [US3] Implement `attention[]` builder in `DashboardService` (omit rating_drop when deltas null).
- [X] T032 [US3] [P] Build `apps/web/components/dashboard/attention-list.tsx` (severity styling, links to `/reviews…` or `/organizations/[id]`).
- [X] T033 [US3] Wire `attention-list` into the overview page.

---

## Phase 6: User Story 5 — Filters (P2)

**Goal**: Period / platform / organization filters recompute the whole page.

**Independent test**: change each filter → all blocks recompute; org filter narrows; platform filter narrows to one platform.

- [X] T034 [US5] [TDD] Extend `test_dashboard_overview.py`: `platform=yandex`/`gis2` narrows; `org_ids` restricts; `company_id` scopes.
- [X] T035 [US5] Filter narrowing applied consistently through every block via `_selected_orgs` + `_review_query` (platform filter).
- [X] T036 [US5] [P] Build `apps/web/components/dashboard/dashboard-filters.tsx` (period + platform chips + organization multiselect dropdown).
- [X] T037 [US5] Persist filter state in URL `searchParams` (period/platform/org_ids) via `router.replace`; page reads from `useSearchParams` (Suspense-wrapped).

---

## Phase 7: User Story 4 — Worst locations & trending aspects (P3)

**Goal**: Top-10 worst-locations table + trending-negative-aspects table.

**Independent test**: varied org ratings/unanswered → worst-locations ordered rating asc with unanswered; problems across two 7d windows → trending table shows change + sentiment split.

- [X] T038 [US4] [TDD] Extend `test_dashboard_overview.py`: `worst_locations` (≤10, rating asc, delta null-safe, unanswered) and `trending_aspects` (mentions, change_percent, sentiment split).
- [X] T039 [US4] Implement `worst_locations[]` + `trending_aspects[]` in `DashboardService`.
- [X] T040 [US4] [P] Build `apps/web/components/dashboard/worst-locations-table.tsx`.
- [X] T041 [US4] [P] Build `apps/web/components/dashboard/trending-aspects-table.tsx`.
- [X] T042 [US4] Wire the two US4 tables into the overview page.

---

## Phase 8: Polish & cross-cutting

- [X] T043 [P] Playwright e2e `apps/web/tests/overview.spec.ts`: unauth redirect + root→overview smokes (headless); authed render + filter-URL suite gated on `E2E_ADMIN_EMAIL`/`E2E_ADMIN_PASSWORD`.
- [X] T044 [P] Responsive pass: responsive grids (1→3 cols); tables wrapped in `overflow-x-auto` so the body never scrolls horizontally.
- [X] T045 Gate: `pytest` 193 passed; `next build` + `next lint` + `tsc` clean. Full `test:e2e` render suite needs live API+web+Postgres + seeded admin (skipped without creds).
- [X] T046 [P] Updated `docs/plans/dashboard_new/overview-implementation-plan.md` with SHIPPED status + pointer to spec 009.

---

## Dependencies

- **Setup + Foundational** → all user stories. Complete.
- **US1** = MVP. Complete.
- **US2, US3, US5** (P2) depend on Foundational; independent of each other.
- **US4** (P3) depends on Foundational; independent.
- **Polish** after shipped stories.

## MVP scope

**Phases 1–3 shipped**: network pulse (header + hero + strip KPIs) on the dashboard landing page, with period/platform filtering. US2/US3/US5 then US4 add the remaining blocks incrementally.
