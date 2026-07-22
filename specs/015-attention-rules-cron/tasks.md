---
description: "Task list for Attention Rules Cron Model"
---

# Tasks: Attention Rules Cron Model

**Input**: Design documents from `specs/015-attention-rules-cron/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: INCLUDED — Constitution Principle III (critical-path testing) requires automated tests
for state-machine logic, evaluation semantics, and API contracts before merge.

**Organization**: Grouped by user story. US1 and US2 are both P1 and share the evaluator built in
Foundational; US1 = "latched feed produced by the sweep + shown on /overview", US2 = "period
lifecycle + restart". US3 = history view, US4 = period field in management UI.

## Path Conventions

Monorepo web app: backend `apps/api/app/…`, backend tests `apps/api/tests/…`, web
`apps/web/…`. Paths are repository-relative.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: No new project scaffolding — feature extends existing modules. Only groundwork.

- [X] T001 Add `min_count` semantics note and confirm no new dependency is needed; verify next Alembic revision id is `0023` by inspecting `apps/api/alembic/versions/` (head is `0022_response_date`).

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Data model, schemas, and the reusable evaluator that ALL user stories depend on.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T002 Extend `AttentionRule` model with `period_days` (Integer, not null, default 1), `window_started_at` (`DateTime(timezone=True)`, not null), `latched_at` (`DateTime(timezone=True)`, nullable) in `apps/api/app/models/attention_rule.py`.
- [X] T003 [P] Create `AttentionEvent` model (`id`, `rule_id` FK→attention_rules ON DELETE CASCADE, `fired_at`, `type`, `severity`, `title`, `subtitle` nullable, `value` Float, `link`, `created_at`) with index `ix_attention_events_rule_fired` on `(rule_id, fired_at)` in `apps/api/app/models/attention_event.py`; register it in `apps/api/app/models/__init__.py`.
- [X] T004 Write Alembic migration `apps/api/alembic/versions/0023_attention_events_and_lifecycle.py`: add the three `attention_rules` columns (backfill `period_days=1`, `window_started_at=created_at`, `latched_at=NULL`), create `attention_events` table + FK cascade + index; implement downgrade. Reuse existing PG enum types `attention_rule_type_enum` / `attention_severity_enum` for the event columns.
- [X] T005 Rework `PARAM_MODELS` in `apps/api/app/schemas/attention_rule.py`: drop `hours` from `UnansweredOverdueParams` (add `min_count: int = 1, ge=1`), drop `window_hours` from `FreshNegativeParams` (add `min_count`), add `min_count` to `EscalatedParams`; keep `rating_drop`/`aspect_spike` params.
- [X] T006 Add `period_days` to `AttentionRuleCreate` (default 1, ge=1), `AttentionRuleUpdate` (optional, ge=1), and to `AttentionRuleResponse` with derived `is_latched`, `window_started_at`, `latched_at`, `period_ends_at`; add `AttentionEventResponse`, `AttentionEventListResponse`, and `AttentionRuleRestartResponse` schemas in `apps/api/app/schemas/attention_rule.py`.
- [X] T007 Create `AttentionEvaluator` service skeleton in `apps/api/app/services/attention_evaluator.py`: constructor `(db, now_factory)`, and **move** the condition logic out of `DashboardService` — `evaluate_rule(rule, window_start, now) -> list[Item]`, rule-scope resolution (`_rule_scope_ids` / `_evaluate_rule` bodies), `_scoped_count`, snapshot-baseline helper, `_rating_drops`, `_aspect_spikes` — re-windowed to `[window_start, now]` per data-model (unanswered/fresh_negative use `first_seen_at ∈ W` + `min_count`; escalated ignores window; rating_drop baseline at `window_start`; aspect_spike baseline `[window_start − period_days, window_start]`).
- [X] T008 [P] Extend `DEFAULT_RULES` / `seed_defaults` in `apps/api/app/services/attention_rule_service.py` to include `period_days` (default 1), and make `create`/`update` accept and validate `period_days`; set `window_started_at=now`, `latched_at=None` on create.
- [X] T009 [P] Add `period_days`, `window_started_at`, `latched_at`, `is_latched`, `period_ends_at`, and an `AttentionEvent`/restart-response types to `apps/web/lib/types.ts`; add `restartAttentionRule` and `getAttentionRuleEvents` calls to `apps/web/lib/api.ts`.

**Checkpoint**: Model, migration, schemas, evaluator condition logic, and web types exist. `alembic upgrade head` applies cleanly.

---

## Phase 3: User Story 1 — Latched attention feed driven by the sweep (Priority: P1) 🎯 MVP

**Goal**: A background sweep evaluates rules and latches them; `/overview` shows the latched
events from stored snapshots, ignoring page filters.

**Independent Test**: Seed a rule whose condition holds, run `AttentionEvaluator.sweep(now=t0)`,
then load `/api/dashboard/overview` and confirm the `attention` block shows the fired event from
stored state (and is unchanged by period/platform/org filters).

### Tests for User Story 1

- [X] T010 [P] [US1] Write `apps/api/tests/test_attention_evaluator.py` covering `sweep`: a met condition latches + inserts events; second `sweep` at same/near `now` creates no duplicates (idempotent, FR-007); disabled rule skipped (FR-008); one failing rule doesn't abort others (FR-009). (Write first, expect fail.)
- [X] T011 [P] [US1] Adapt `apps/api/tests/test_dashboard_attention_rules.py` and `apps/api/tests/test_dashboard_overview.py` so the `attention` block is asserted from stored `attention_events` (latched rules), with the unchanged item shape and severity/magnitude ordering (FR-018/020/021), and independent of page filters (FR-019).

### Implementation for User Story 1

- [X] T012 [US1] Implement `AttentionEvaluator.sweep(now)` in `apps/api/app/services/attention_evaluator.py`: iterate enabled rules (row-locked per rule), do rollover, evaluate-if-armed, latch + insert `AttentionEvent` snapshots; per-rule try/except + commit; return fired count.
- [X] T013 [US1] Implement `AttentionEvaluator.current_block_items()`: query `attention_events` joined to enabled+latched rules where `fired_at == rule.latched_at`, map to item dicts, sort by severity rank then `-abs(value)`.
- [X] T014 [US1] Replace `DashboardService._attention(...)` usage in `apps/api/app/services/dashboard_service.py`: `overview` now calls `AttentionEvaluator(self.db).current_block_items()` for the `attention` block; delete the live `_attention`/`_evaluate_rule`/`_eval_*`/`_rating_drops`/`_aspect_spikes` bodies now living in the evaluator (keep helpers still used by other blocks, e.g. `_delta_for`, `_aspect_rows`, `_scoped_filters`).
- [X] T015 [US1] Register the 30-minute sweep in `apps/api/app/services/job_scheduler.py`: add `run_attention_sweep()` (own `SessionLocal`, calls `AttentionEvaluator(db).sweep()`, closes in finally) and register it in `sync_all()` as cron `*/30 * * * *` (`timezone="Europe/Moscow"`, `id="attention-sweep"`, `replace_existing=True`).
- [X] T016 [US1] Confirm `apps/web/components/dashboard/attention-list.tsx` renders unchanged from the stored-event item shape; adjust only if a field name changed (it should not).

**Checkpoint**: Running the sweep populates the `/overview` block from stored state; page filters don't affect it. MVP is demoable.

---

## Phase 4: User Story 2 — Period, auto-rollover, and manual restart (Priority: P1)

**Goal**: Each rule has a period; the sweep rolls the window forward when it elapses; an
admin can restart a rule for immediate re-evaluation.

**Independent Test**: Fire a rule, advance `now` past `window_started_at + period_days`, sweep,
confirm re-arm + possible re-fire. Separately, call the restart endpoint and confirm immediate
window reset + re-evaluation in the response.

### Tests for User Story 2

- [X] T017 [P] [US2] Write `apps/api/tests/test_attention_sweep.py`: rollover after firing (FR-005), never-fired rollover so window doesn't grow unbounded (US2 AC2), `period_days` respected, and the ARMED↔LATCHED transitions across successive `sweep(now=…)` ticks.
- [X] T018 [P] [US2] Extend `apps/api/tests/test_attention_rules_api.py` with restart: `POST /api/attention-rules/{id}/restart` resets window, re-evaluates, returns `{rule, events}`; admin-only (401 unauth, 403 non-admin); 404 unknown id.

### Implementation for User Story 2

- [X] T019 [US2] Implement `AttentionEvaluator.restart(rule_id, now) -> RestartResult | None` in `apps/api/app/services/attention_evaluator.py`: set `window_started_at=now`, `latched_at=None`, run the single-rule evaluate/latch step synchronously, return updated rule + events created now (None if rule missing).
- [X] T020 [US2] Add `POST /api/attention-rules/{id}/restart` (admin, `require_admin`) to `apps/api/app/api/attention_rules.py` returning `AttentionRuleRestartResponse`; 404 when the rule doesn't exist.
- [X] T021 [US2] In `apps/web/app/(dashboard)/attention-rules/page.tsx` (+ a client component under `apps/web/components/attention-rules/`), show per-rule status (сработало/ждёт with `period_ends_at`) and a **Перезапустить** button wired to `restartAttentionRule`, refreshing the row from the response.

**Checkpoint**: Rules re-arm on period expiry via the sweep; operators can restart and see immediate results.

---

## Phase 5: User Story 3 — Per-rule firing history (Priority: P2)

**Goal**: Operators can view the chronological history of a rule's firings.

**Independent Test**: Fire a rule across several periods, call the events endpoint, and confirm
each firing appears with its `fired_at` and snapshot.

### Tests for User Story 3

- [X] T022 [P] [US3] Extend `apps/api/tests/test_attention_rules_api.py`: `GET /api/attention-rules/{id}/events` returns firings newest-first with snapshot fields; empty list for a never-fired rule; 404 unknown id; cascade delete removes events (FR-024).

### Implementation for User Story 3

- [X] T023 [US3] Add `list_events(rule_id, limit)` to `apps/api/app/services/attention_rule_service.py` (or the evaluator) and `GET /api/attention-rules/{id}/events` (auth) to `apps/api/app/api/attention_rules.py` returning `AttentionEventListResponse`.
- [X] T024 [US3] Add an expandable per-rule **history** view in `apps/web/components/attention-rules/` (grouping events by `fired_at`), fed by `getAttentionRuleEvents`, with an explicit empty state.

**Checkpoint**: History is viewable per rule.

---

## Phase 6: User Story 4 — Period field in rule management (Priority: P2)

**Goal**: Operators set/edit the trigger period (days) on create/edit.

**Independent Test**: Create/edit a rule via the form with a period, confirm it persists and is
validated (≥1).

### Tests for User Story 4

- [X] T025 [P] [US4] Extend `apps/api/tests/test_attention_rules_api.py`: create/patch with `period_days` persists; `period_days=0`/negative → 422; unknown param key → 422; default 1 when omitted (FR-001/003).

### Implementation for User Story 4

- [X] T026 [US4] Add a **Период (дней)** input (integer ≥1, default 1) to the rule create/edit form in `apps/web/components/attention-rules/` and `apps/web/app/(dashboard)/attention-rules/page.tsx`, sending `period_days` through `lib/api.ts`.

**Checkpoint**: Period is configurable from the UI.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [X] T027 [P] Ensure `apps/api/tests/test_query_counts.py` still asserts the `/overview` SELECT count scales with neither org nor review volume, now that the `attention` block reads only `attention_events` (add/adjust the guard for the new read path).
- [X] T028 Update `CLAUDE.md` architecture notes (attention block is now cron-driven/stateful; window `[window_started_at, now]` replaces per-type windows; new `attention_events` table and `AttentionEvaluator`).
- [X] T029 Run the quickstart validation gate: `pytest -v` (apps/api) green, then `npm run lint && npm run test:e2e` (apps/web); confirm read-only invariant (SC-006).

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: none.
- **Foundational (Phase 2)**: after Setup — BLOCKS all user stories (model/migration/schemas/evaluator).
- **US1 (Phase 3)**: after Foundational. Delivers the MVP (sweep → stored events → overview).
- **US2 (Phase 4)**: after Foundational; shares the evaluator with US1 (do US1 first for a demoable slice, but the restart/rollover code is additive to the same file — coordinate edits to `attention_evaluator.py`).
- **US3 (Phase 5)** and **US4 (Phase 6)**: after Foundational; independent of US1/US2 internals (history endpoint + period field). Can run in parallel with US2.
- **Polish (Phase 7)**: after the desired stories.

### Within Each User Story

- Tests written first and expected to fail, then implementation.
- Model → schema → service (evaluator) → endpoint → UI.

### Parallel Opportunities

- Foundational: T003, T008, T009 marked [P] (different files) after T002.
- Tests across stories (T010, T011, T017, T018, T022, T025) are [P] where they touch different files — note T018/T022/T025 all edit `test_attention_rules_api.py`, so serialize those three.
- US3 and US4 can be built in parallel with US2 once Foundational is done.
- **Contention**: T007/T012/T013/T019 all edit `attention_evaluator.py` → serialize. T014 edits `dashboard_service.py`. T020/T023 edit `api/attention_rules.py` → serialize.

---

## Implementation Strategy

### MVP First (US1)

1. Phase 1 Setup → Phase 2 Foundational → Phase 3 US1.
2. STOP and validate: run the sweep, confirm `/overview` shows latched events independent of filters.
3. Demo.

### Incremental Delivery

US1 (MVP) → US2 (period/rollover/restart) → US3 (history) + US4 (period field) → Polish.

---

## Notes

- [P] = different files, no dependency. Serialize tasks touching the same file (see Contention).
- The dedup contract (`build_review_hash`, `uq_review_org_hash`) is untouched.
- The sweep stays off in pytest via the existing `jobs_scheduler_enabled` gate; tests call
  `AttentionEvaluator.sweep(now=…)` directly with an injected clock.
- Commit after each task or logical group; keep ORM changes additive.
