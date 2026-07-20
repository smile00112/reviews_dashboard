---

description: "Task list for feature 014 — Ratings Page"
---

# Tasks: Ratings Page

**Input**: Design documents from `/specs/014-ratings-page/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/dashboard-ratings.md](./contracts/dashboard-ratings.md)

**Tests**: INCLUDED — Constitution Principle III (Critical-Path Testing) requires automated coverage of new aggregation logic and API contracts before merge.

**Organization**: Tasks grouped by user story. The page is served by **one** endpoint whose payload has five blocks; Foundational delivers the endpoint returning empty blocks, then each story fills its own block(s) end to end (service helper → payload wiring → component → page). This keeps every story independently implementable, testable, and demoable.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- Exact file paths included in every task

## Path Conventions

Web application monorepo per [plan.md](./plan.md): backend `apps/api/app/`, backend tests `apps/api/tests/`, frontend `apps/web/`.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create the directories and test module this feature adds. No project initialization needed — this is additive to an existing monorepo.

- [X] T001 Create the route directory `apps/web/app/(dashboard)/ratings/` and the component directory `apps/web/components/dashboard/ratings/`
- [X] T002 [P] Create the backend test module `apps/api/tests/test_dashboard_ratings.py` with the shared fixtures (seeded organizations, Yandex reviews across ratings/dates, Google/2ГИС aggregates, rating snapshots), following the fixture style of `apps/api/tests/test_dashboard_overview.py`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The endpoint, schema, service entry point, and page shell that every block plugs into.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T003 Add the `DashboardRatings` response models and all nested models (`PlatformDistributionRow`, `StarShare`, `TrendBlock`, `TrendSeries`, `ResponseSpeedBlock`, `WeekdayBlock`, `WeekdayStat`) to `apps/api/app/schemas/dashboard.py`, matching [data-model.md](./data-model.md) null semantics (nullable fields default to `None`, never `0`)
- [X] T004 Add dialect-aware private bucket helpers to `apps/api/app/services/dashboard_service.py`: `_month_key_expr()`, `_week_key_expr()`, `_weekday_expr()` — each branching on `self.db.get_bind().dialect.name == "sqlite"` per [research.md](./research.md) §2–4
- [X] T005 Add the `DashboardService.ratings(...)` entry point to `apps/api/app/services/dashboard_service.py` — resolve `period`/`date_from`/`date_to` into `cutoff` + `until` via `PERIOD_DAYS`/`CUSTOM_PERIOD`, resolve orgs via `_selected_orgs`, apply the `scope = None` whole-network optimization, and return a fully-empty payload (empty blocks, `null` aggregates) so the contract holds before any block is implemented (depends on T003, T004)
- [X] T006 Add the `GET /api/dashboard/ratings` route to `apps/api/app/api/dashboard.py` — `get_current_user` auth, `PERIOD_DAYS`/`_PLATFORMS` validation, and the four 422 cases from [contracts/dashboard-ratings.md](./contracts/dashboard-ratings.md); delegate to `DashboardService.ratings` and validate through `DashboardRatings` (depends on T005)
- [X] T007 [P] Add contract tests to `apps/api/tests/test_dashboard_ratings.py`: unauthenticated → 401; unknown `period` → 422; unknown `platform` → 422; `period=custom` missing a bound → 422; `date_from > date_to` → 422; org filter matching nothing → 200 with empty blocks (depends on T006)
- [X] T008 [P] Add `DashboardRatings` and all nested types to `apps/web/lib/types.ts`, mirroring the backend schema field-for-field
- [X] T009 [P] Add `getDashboardRatings(params)` to `apps/web/lib/api.ts` following the `getDashboardOverview` query-string builder (depends on T008)
- [X] T010 Create the page shell `apps/web/app/(dashboard)/ratings/page.tsx` as a client component reusing `DashboardFilters`, with URL-driven state (`period`, `platform`, `org_ids`, `company_id`, `from`, `to`) and the same malformed-param fallbacks as `apps/web/app/(dashboard)/overview/page.tsx`; render empty block placeholders (depends on T009)
- [X] T011 [P] Add the «Рейтинги» nav item (`/ratings`) to the "Обзор" group in `apps/web/components/shell/sidebar.tsx`

**Checkpoint**: `/ratings` loads, is authenticated, honors filters, and returns a valid empty payload. Block implementation can now begin.

---

## Phase 3: User Story 1 — Compare rating quality across platforms (Priority: P1) 🎯 MVP

**Goal**: The per-platform distribution table — average rating, 5★→1★ shares, removed count — with «нет данных» where per-review data does not exist.

**Independent Test**: Load `/ratings` for organizations with collected reviews and Google aggregates; the table shows one row per platform, Yandex and 2ГИС with a full star breakdown and removed count, Google with an aggregate rating and «нет данных» in the per-star and removed columns.

### Tests for User Story 1

> Write these first and confirm they fail before implementing.

- [X] T012 [P] [US1] In `apps/api/tests/test_dashboard_ratings.py`, test the Yandex distribution: the five star `count`s sum to `total_reviews`, `share` percentages are computed from active reviews, and removed reviews are excluded from shares but counted in `removed_count` (SC-002, FR-003)
- [X] T013 [P] [US1] In `apps/api/tests/test_dashboard_ratings.py`, test that the Google row carries a non-null `avg_rating` from the organization aggregates but `stars is None` and `removed_count is None`, and that 2ГИС (which *is* collected per-review) gets a real star breakdown (FR-004)
- [X] T014 [P] [US1] In `apps/api/tests/test_dashboard_ratings.py`, test that `platform=yandex` narrows `platform_distribution` to the Yandex row, and that an org/company filter narrows the counts (FR-010)

### Implementation for User Story 1

- [X] T015 [US1] Implement the private `_platform_distribution(...)` helper in `apps/api/app/services/dashboard_service.py`: one grouped scan (`GROUP BY rating`) over scoped reviews using `_scoped_filters` + `_published_expr`, with conditional counts splitting active (`removed_at IS NULL`) from removed rows; build the Google row from `Organization.google_rating` weighted by `google_review_count`, leaving `stars`/`removed_count` as `None` (`_PER_REVIEW_PLATFORMS` = {yandex, gis2}) (depends on T005)
- [X] T016 [US1] Wire `platform_distribution` into the `DashboardService.ratings(...)` payload in `apps/api/app/services/dashboard_service.py` (depends on T015)
- [X] T017 [P] [US1] Create `apps/web/components/dashboard/ratings/platform-distribution-table.tsx` — platform logo, name, rating pill (high/mid/low by threshold), five star-share columns, the mini stacked distribution bar, and the removed column; render «нет данных» wherever a field is `null`
- [X] T018 [US1] Render the distribution table in `apps/web/app/(dashboard)/ratings/page.tsx` (depends on T010, T017)

**Checkpoint**: US1 is fully functional and independently demoable — the MVP.

---

## Phase 4: User Story 2 — See how ratings and volume trend over time (Priority: P2)

**Goal**: Two monthly trend blocks from `rating_snapshot` — average rating per platform, and review volume per platform.

**Independent Test**: With ≥2 months of snapshots, the dynamics block plots one monthly average-rating line per platform and the volume block plots monthly review counts, both bounded by the selected period; months without snapshots appear as gaps.

### Tests for User Story 2

- [X] T019 [P] [US2] In `apps/api/tests/test_dashboard_ratings.py`, test monthly bucketing: with several snapshots in one month, the **latest** snapshot in that month supplies the month's `rating` and `review_count` (research §2)
- [X] T020 [P] [US2] In `apps/api/tests/test_dashboard_ratings.py`, test that a month with no snapshot yields a `null` point (a gap, not `0`), and that with no snapshot history at all both trend blocks return empty `labels` and empty/`null` series without erroring (FR-005, FR-006, FR-011)

### Implementation for User Story 2

- [X] T021 [US2] Implement the private `_snapshot_trends(...)` helper in `apps/api/app/services/dashboard_service.py` — one grouped query over `RatingSnapshot` bucketed by month key (T004) and platform, taking the latest `captured_on` per (month, platform, org), aggregating across selected orgs (review-count-weighted average rating; summed review counts), bounded by the period; returns both the rating and volume series (depends on T004, T005)
- [X] T022 [US2] Wire `rating_trend` and `volume_trend` into the `DashboardService.ratings(...)` payload in `apps/api/app/services/dashboard_service.py`, assembling ordered `labels` and index-aligned per-platform `points` with `null` gaps (depends on T021)
- [X] T023 [P] [US2] Create `apps/web/components/dashboard/ratings/rating-trend-chart.tsx` — hand-rolled SVG multi-line chart (one path per platform, platform colors, gap-aware path breaks on `null`, y-axis auto-scaled to the rating range) with a legend and an empty state
- [X] T024 [P] [US2] Create `apps/web/components/dashboard/ratings/volume-trend-chart.tsx` — hand-rolled SVG/CSS stacked bar chart (one stack segment per platform per month) with a legend and an empty state
- [X] T025 [US2] Render both trend blocks side by side in `apps/web/app/(dashboard)/ratings/page.tsx` (depends on T010, T023, T024)

**Checkpoint**: US1 and US2 both work independently.

---

## Phase 5: User Story 3 — Judge responsiveness and timing patterns (Priority: P3)

**Goal**: The weekly response-speed block (median/p95 vs a fixed SLA target) and the Mon–Sun weekday breakdown with a best/worst-day insight.

**Independent Test**: With answered Yandex reviews carrying response timestamps and review dates, the response block shows weekly median and p95 series against the target line, and the weekday block shows seven days with counts, average ratings, and an insight naming the worst- and best-rated weekday.

### Tests for User Story 3

- [X] T026 [P] [US3] In `apps/api/tests/test_dashboard_ratings.py`, test weekly response bucketing: reviews answered in distinct weeks land in distinct labeled buckets, `median_minutes`/`p95_minutes` are index-aligned with `labels`, and `sla_target_minutes` echoes the settings constant (FR-007)
- [X] T027 [P] [US3] In `apps/api/tests/test_dashboard_ratings.py`, test the weekday block: exactly 7 entries ordered Mon→Sun, `count` reflects reviews on that weekday, a weekday with no reviews has `count == 0` and `avg_rating is None`, reviews with `review_date IS NULL` are excluded from this block only, and `insight` names the lowest- and highest-average weekday (FR-008, FR-009)

### Implementation for User Story 3

- [X] T028 [US3] Implement the private `_response_speed_weekly(...)` helper in `apps/api/app/services/dashboard_service.py` — reuse `_response_delay_expr()`, group answered scoped reviews by week key (T004), compute median/p95 per week via `percentile_cont` on PostgreSQL with the `statistics.median` + `_percentile` fallback on SQLite (mirroring `_response_percentiles`), and read the SLA target from `SettingsService.sla_threshold_minutes()` (depends on T004, T005)
- [X] T029 [P] [US3] Implement the private `_weekday_stats(...)` helper in `apps/api/app/services/dashboard_service.py` — group scoped active reviews by weekday (T004) over `review_date`, producing `count` and `avg(rating)`, normalized to Mon→Sun with zero-filled missing days, plus the Russian best/worst-weekday `insight` string built in Python (depends on T004, T005)
- [X] T030 [US3] Wire `response_speed` and `weekday` into the `DashboardService.ratings(...)` payload in `apps/api/app/services/dashboard_service.py` (depends on T028, T029)
- [X] T031 [P] [US3] Create `apps/web/components/dashboard/ratings/response-speed-chart.tsx` — hand-rolled SVG with a solid median line, a dashed p95 line, a dashed constant SLA target line, minute-formatted axis, legend, and empty state
- [X] T032 [P] [US3] Create `apps/web/components/dashboard/ratings/weekday-breakdown.tsx` — seven CSS rows (Пн–Вс) with a volume bar and an average-rating cell colored by threshold (≤4.0 bad / 4.0–4.5 warn / ≥4.5 good), plus the insight line beneath
- [X] T033 [US3] Render the response-speed and weekday blocks in `apps/web/app/(dashboard)/ratings/page.tsx` (depends on T010, T031, T032)

**Checkpoint**: All three user stories are independently functional; the page matches the prototype's `screen-rating` minus the intentionally-dropped hour-of-day axis.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [X] T034 [P] Add a query-count guard to `apps/api/tests/test_dashboard_ratings.py` in the style of `apps/api/tests/test_query_counts.py`, asserting the SQL statement count for `/api/dashboard/ratings` grows with neither organization count nor review volume (plan Performance Goals)
- [X] T035 [P] Add the E2E smoke `apps/web/tests/ratings.spec.ts` — page renders all blocks, a filter change updates the URL and refetches, following the gating style of `apps/web/tests/overview.spec.ts`
- [X] T036 [P] Document the feature in `CLAUDE.md` — a "Ratings page (feature 014)" architecture subsection covering the endpoint, the snapshot-based trend sourcing, and the weekday-only (no hour-of-day) constraint
- [X] T037 Run the verification gate: `pytest -v` in `apps/api`, then `npm run lint` and `npm run test:e2e` in `apps/web`; fix any failures
- [X] T038 Walk the 13 validation scenarios in [quickstart.md](./quickstart.md) against a running stack and confirm each expected outcome

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: no dependencies — start immediately
- **Foundational (Phase 2)**: depends on Setup — **BLOCKS all user stories**
- **User Stories (Phases 3–5)**: all depend on Foundational; independent of each other afterwards
- **Polish (Phase 6)**: depends on the user stories being complete

### User Story Dependencies

- **US1 (P1)**: starts after Phase 2. No dependency on other stories.
- **US2 (P2)**: starts after Phase 2. Independent of US1 (different service helper, different components).
- **US3 (P3)**: starts after Phase 2. Independent of US1 and US2.

Each story touches `DashboardService.ratings(...)` and `page.tsx` for its wiring task — those wiring tasks (T016, T022, T030 and T018, T025, T033) serialize against each other per file, which is why they are not marked `[P]`.

### Within Each User Story

- Tests written and failing before implementation
- Service helper → payload wiring → component → page render
- Story complete before moving to the next priority

### Parallel Opportunities

- T002 runs alongside T001
- T007, T008, T009, T011 run in parallel once their dependencies land
- All test tasks within a story ([P]) run in parallel
- Chart components within a story (T023/T024, T031/T032) run in parallel
- With multiple developers, US1/US2/US3 proceed simultaneously after Phase 2
- Polish tasks T034, T035, T036 run in parallel

---

## Parallel Example: User Story 1

```bash
# Tests first, in parallel:
Task: "Yandex distribution star-sum & removed-split test in apps/api/tests/test_dashboard_ratings.py"
Task: "Google/2ГИС null stars & removed test in apps/api/tests/test_dashboard_ratings.py"
Task: "Platform/org filter narrowing test in apps/api/tests/test_dashboard_ratings.py"

# Then implementation — service helper, with the component in parallel:
Task: "_platform_distribution helper in apps/api/app/services/dashboard_service.py"
Task: "platform-distribution-table.tsx in apps/web/components/dashboard/ratings/"
```

---

## Implementation Strategy

### MVP First (User Story 1 only)

1. Phase 1: Setup
2. Phase 2: Foundational (**critical — blocks everything**)
3. Phase 3: User Story 1
4. **STOP and VALIDATE**: the distribution table answers "which platform drags us down?" on its own
5. Demo if ready

### Incremental Delivery

1. Setup + Foundational → `/ratings` live with empty blocks
2. + US1 → distribution table → demo (**MVP**)
3. + US2 → trends → demo
4. + US3 → response speed + weekday → demo
5. Polish → query-count guard, E2E, docs, verification gate

---

## Notes

- `[P]` = different files, no incomplete dependencies
- The three trailing blocks degrade to empty states, so shipping US1 alone leaves no broken UI
- No migration, no new dependency, no write path — keep it that way (Constitution II, V)
- `null` never renders as `0`; it renders as «нет данных» or a line gap
- Commit after each task or logical group
