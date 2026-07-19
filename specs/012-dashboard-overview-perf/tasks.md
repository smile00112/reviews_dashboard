# Tasks: Dashboard Overview Performance

**Input**: Design documents from `/specs/012-dashboard-overview-perf/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/overview-unchanged.md, quickstart.md

**Tests**: Included — the constitution's critical-path rule applies (payload identity is the contract; existing suites must stay green unmodified, plus one new query-budget guard).

**Organization**: US1 = the aggregation rewrite (MVP, delivers the speedup); US2 = filtered-path guarantees.

## Format: `[ID] [P?] [Story] Description`

## Phase 1: Setup

- [X] T001 Capture pre-change behavior baseline: run `pytest tests/test_dashboard_overview.py tests/test_dashboard_attention_rules.py tests/test_query_counts.py -v` in `apps/api` and confirm green (these files are the frozen contract — they must not be edited in later tasks). Optionally capture a live payload baseline per quickstart.md §4 if the dev stack is running.

---

## Phase 2: Foundational (Blocking Prerequisites)

- [X] T002 [P] Add additive indexes to `apps/api/app/models/review.py` `__table_args__`: partial `ix_reviews_org_unanswered` (`organization_id` WHERE `response_text IS NULL`, with both `postgresql_where` and `sqlite_where`) and composite `ix_reviews_org_platform_first_seen` (`organization_id`, `platform`, `first_seen_at`), per data-model.md.
- [X] T003 [P] Create Alembic migration `apps/api/alembic/versions/0017_dashboard_overview_indexes.py` adding both indexes (reversible downgrade; partial index via `postgresql_where`), chained after 0016.
- [X] T004 [P] Add dialect-aware datetime bind helper `_dt_param` to `apps/api/app/services/dashboard_service.py`: converts aware-UTC cutoffs to naive UTC when `self.db.get_bind().dialect.name == "sqlite"`, passes aware through on PostgreSQL (research.md R2).

**Checkpoint**: schema + helper ready; rewrite can begin.

---

## Phase 3: User Story 1 — Fast overview load (Priority: P1) 🎯 MVP

**Goal**: overview computed from fixed-count SQL aggregates + narrow loads; payload identical; <300 ms.

**Independent Test**: `pytest tests/test_dashboard_overview.py tests/test_dashboard_attention_rules.py tests/test_query_counts.py -v` green with zero edits to the two dashboard suites; live timing per quickstart.md §3.

- [X] T005 [US1] Implement aggregate queries A1–A4 in `apps/api/app/services/dashboard_service.py`: A1 single-row counters (`case()`-based conditional counts + `MIN(first_seen_at)` for `_span_days`), A2 rating `GROUP BY`, A3 sentiment `GROUP BY` (NULL bucket separate), A4 per-org unanswered `GROUP BY` — all scoped by selected org ids + optional platform, cutoffs bound via `_dt_param` (query shapes in data-model.md).
- [X] T006 [US1] Implement A5 platform-cards aggregate (`GROUP BY platform`: rated count, negatives ≤2★, response-delay sum+count over period rows, platform-agnostic) in `dashboard_service.py`, removing the second full scan at `_platform_cards`; keep negativity %/avg-hours rounding in Python.
- [X] T007 [US1] Implement narrow loads R1 (`(first_seen_at, response_first_seen_at)` for period rows with responses → existing median/p95 code) and R2 (`(organization_id, review_date, problems, sentiment)` for `review_date >= now-14d AND problems IS NOT NULL` → `_trending_aspects` / `_aspect_spikes`) in `dashboard_service.py`.
- [X] T008 [US1] Rewrite `_sentiment` and `_kpi_strip` to consume A3/R1 results: reproduce `summarize()` percent formula `round(part/n*100, 1)` with `n = analyzed_total` exactly (research.md R3); `summarize()` itself and `analysis/` stay untouched.
- [X] T009 [US1] Rewrite `_attention` count-type rules (`unanswered_overdue`, `fresh_negative`, `escalated`) as per-rule scoped `COUNT` queries honoring `rule.params` and rule org-scope ∩ page filters; `aspect_spike` consumes R2 data; `rating_drop` unchanged; item ordering/severity sort unchanged (research.md R4).
- [X] T010 [US1] Rewire `overview()` to the new data access: drop `base.all()` / `all_reviews` / `period_reviews` materialization, feed all blocks (`_header`, `_kpi_hero`, `_rating_distribution`, `_worst_locations` unanswered map, etc.) from A1–A5/R1–R2; keep every `round()`, sort, tie-break, and top-N in Python (research.md R7); `_worst_locations` still iterates `orgs`.
- [X] T011 [US1] Extend `apps/api/tests/test_query_counts.py` with `test_overview_query_count_does_not_scale_with_reviews`: same SELECT count at 30 vs 300 reviews for a fixed org set (contract: overview-unchanged.md performance table). Do not modify existing tests.
- [X] T012 [US1] Verify US1: `cd apps/api && pytest tests/test_dashboard_overview.py tests/test_dashboard_attention_rules.py tests/test_query_counts.py tests/test_rating_snapshot.py -v` — all green, dashboard suites unmodified (`git diff --stat` shows no changes to them).

**Checkpoint**: MVP done — overview fast and value-identical.

---

## Phase 4: User Story 2 — Filtered views stay fast (Priority: P2)

**Goal**: platform/company/org filters never cost more than the unfiltered view; empty selection short-circuits.

**Independent Test**: filtered requests return identical payloads to pre-change behavior and issue the same bounded query count.

- [X] T013 [P] [US2] Add filtered-path cases to `apps/api/tests/test_query_counts.py`: SELECT count with `platform="yandex"` ≤ SELECT count with `platform="all"` on the same data (no second scan), and `overview()` with an empty org selection issues no review queries (returns `_empty_payload` immediately).
- [X] T014 [US2] Confirm filter semantics preserved in `dashboard_service.py`: `platform` filter applied to A1–A4/R1/R2 but NOT A5 (platform cards stay platform-agnostic, as today); `org_ids`/`company_id` scoping identical; run `pytest tests/test_dashboard_overview.py -v` (filter cases) green.

---

## Phase 5: Polish & Cross-Cutting

- [X] T015 Migration round-trip check per quickstart.md §2: `alembic upgrade head`, `alembic downgrade -1`, `alembic upgrade head` against local Postgres.
- [X] T016 Full verification gate: `cd apps/api && pytest -v` (entire suite), then live timing + payload-identity spot-check per quickstart.md §3–§4 if the dev stack is available; record before/after timings in the PR description.

---

## Dependencies

- Phase 2 (T002–T004) blocks Phase 3; T002/T003/T004 are mutually parallel.
- T005 → T006/T007 (same file, sequential); T008 needs T005+T007; T009 needs T007; T010 needs T005–T009; T011 needs T010; T012 needs T011.
- Phase 4 needs Phase 3 complete (T013 parallel-safe with T014 prep, different concerns but same test file as T011 — run after T012).
- Phase 5 last.

## Parallel Example

Phase 2: T002, T003, T004 simultaneously (different files/functions). Phases 3–4 are largely sequential — one service file.

## Implementation Strategy

MVP = Phases 1–3 (the rewrite + guard). Phase 4 adds filtered-path guarantees; Phase 5 is the merge gate. Single service file rewrite — prefer one coherent pass over T005–T010 with the contract suites run after each task.
