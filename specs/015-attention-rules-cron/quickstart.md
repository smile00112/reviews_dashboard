# Quickstart / Validation: Attention Rules Cron Model

Prerequisites: API deps installed (`pip install -e ".[dev]"`), migrations applied
(`alembic upgrade head` → includes `0023`), Postgres running. For unit runs, SQLite via pytest
is enough. The APScheduler sweep is **off** under pytest (conftest sets
`JOBS_SCHEDULER_ENABLED=false`); tests drive `AttentionEvaluator.sweep(now=...)` directly with an
injected clock.

## 1. Automated tests (primary gate)

```bash
cd apps/api
pytest -v \
  tests/test_attention_evaluator.py \
  tests/test_attention_sweep.py \
  tests/test_attention_rules_api.py \
  tests/test_dashboard_attention_rules.py \
  tests/test_dashboard_overview.py \
  tests/test_query_counts.py
```

Expected coverage:
- **Lifecycle**: a rule with a met condition latches on `sweep(now=t0)`; a second
  `sweep(now=t0+10min)` creates **no** new events (still latched). Advancing to
  `sweep(now=window_started_at+period_days)` rolls over (new window, `latched_at` cleared) and
  can latch again.
- **Never-fired rollover**: a rule whose condition is never met still has its window advanced
  after `period_days` (window does not grow unbounded).
- **Per-type semantics** over `[window_started_at, now]`: unanswered/fresh_negative count only
  reviews first seen in the window and honor `min_count`; escalated counts current escalated
  regardless of window; rating_drop uses the snapshot baseline at `window_started_at`;
  aspect_spike compares the window to the preceding equal-length window.
- **Restart**: `restart(rule_id, now)` resets the window, re-evaluates synchronously, returns the
  updated rule + freshly created events.
- **Disabled skip**: a disabled rule is not evaluated and its old events don't appear in the
  block.
- **Idempotent sweep**: running `sweep` twice at the same `now` yields exactly one firing / one
  event set per rule (no duplicates).
- **Overview reads stored state**: `DashboardService.overview` returns the `attention` block from
  `attention_events` (latched rules) with the unchanged item shape, ignoring page filters;
  `test_query_counts.py` confirms the attention block adds no per-review COUNT that scales with
  volume.

## 2. REST smoke (manual)

```bash
# Auth as admin (session cookie) first, then:
curl -X POST  /api/attention-rules            -d '{"rule_type":"fresh_negative","severity":"urgent","period_days":1,"params":{"max_rating":2,"min_count":1}}'
curl -X PATCH /api/attention-rules/{id}       -d '{"period_days":2}'
curl -X POST  /api/attention-rules/{id}/restart      # → { rule, events }
curl        /api/attention-rules/{id}/events         # firing history
curl        /api/dashboard/overview | jq '.attention'  # latched items, filter-independent
```

Expected: create returns `period_days`, `window_started_at`, `latched_at=null`, `is_latched=false`,
`period_ends_at`. Restart returns the rule + any events. `422` on `period_days:0` or an unknown
param key. `401` unauthenticated; `403` non-admin on create/patch/delete/restart.

## 3. End-to-end (web)

```bash
cd apps/web && npm run dev   # with API + Postgres up
```

- `/attention-rules`: create/edit shows a **Период (дней)** field; each rule shows a
  **сработало / ждёт** status (with when the current period ends), a **Перезапустить** button
  (immediate re-eval), and an expandable **history** of firings.
- `/overview`: the «Требуют внимания» block shows the currently-latched events (snapshots) and
  does **not** change when you switch the page period/platform/organization filters.

## 4. Verification gate

Per README: `pytest -v` (api) green, then `npm run lint && npm run test:e2e` (web) green.
Confirm no writes to any review platform occurred (read-only invariant, SC-006).
