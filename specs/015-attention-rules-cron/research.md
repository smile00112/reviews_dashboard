# Phase 0 Research: Attention Rules Cron Model

## R1 — Scheduler: reuse `JobScheduler` vs. a dedicated scheduler

**Decision**: Register the 30-minute attention sweep inside the existing
`JobScheduler` (`services/job_scheduler.py`), in `sync_all()`, as a static cron/interval
trigger `*/30 * * * *`. No new scheduler instance, no new process.

**Rationale**:
- The constitution (Principle V) forbids queues/extra services and prefers the in-process
  APScheduler already running in the FastAPI lifespan.
- The scheduler is already gated by `settings.jobs_scheduler_enabled` at the lifespan
  (`main.py`) and `conftest.py` forces `JOBS_SCHEDULER_ENABLED=false` in pytest — so the sweep
  is **automatically off in tests** with no new flag (satisfies FR-010).
- `BackgroundScheduler` `job_defaults` already sets `max_instances=1` and `coalesce=True`, so a
  slow sweep cannot overlap itself and missed ticks collapse (satisfies FR-009's overlap clause
  at the scheduler level).

**Alternatives considered**:
- New `AttentionScheduler` + new `ATTENTION_SWEEP_ENABLED` flag — rejected as duplicate
  infrastructure with no benefit; the existing gate already covers the test requirement.
- Piggyback on the `reviews`/`org_metrics` jobs table — rejected: that machinery is per-org
  scrape items and daily cron, semantically wrong for a light, rule-scoped sweep.

## R2 — Sweep entry point & session handling

**Decision**: Add `JobScheduler.run_attention_sweep()` that opens its own `SessionLocal` (like
`purge_old_runs`/`trigger_job`), instantiates `AttentionEvaluator(db)`, calls `evaluator.sweep()`,
and always closes the session in `finally`.

**Rationale**: Matches the existing background-task pattern (own session, not the request
session). The `AttentionEvaluator` holds all logic so the scheduler method stays a thin adapter.

## R3 — Preventing duplicate history on overlap / concurrency

**Decision**: Rely on APScheduler `max_instances=1` (single in-process instance) plus a
guard in the evaluator: a rule is only latched+logged when `latched_at IS NULL` after rollover,
and the transition sets `latched_at` in the same transaction that inserts events. For belt-and-
suspenders against a future second replica, take a row lock (`with_for_update`) per rule during
the sweep, mirroring `JobService.create_run`.

**Rationale**: Single-instance scheduler already prevents overlap in the current deployment;
the `latched_at`-null check makes re-entry idempotent (FR-007, FR-009); the row lock documents
the invariant and is cheap at this scale.

## R4 — Window rollover anchoring

**Decision**: On a sweep tick, if `now >= window_started_at + period_days`, set
`window_started_at = now` (sweep time) and `latched_at = NULL`. Applies whether or not the rule
had fired. No attempt to align to an exact theoretical boundary.

**Rationale**: The spec explicitly chose "начало = сейчас" and accepts up to one-sweep-interval
drift (Assumptions, FR-005). Simpler and avoids accumulating boundary arithmetic.

## R5 — Per-type evaluation over `[window_started_at, now]`

**Decision**: Move the existing `_eval_*`, `_rating_drops`, `_aspect_spikes`, `_scoped_count`
helpers into `AttentionEvaluator` and re-window them:

| Type | New condition (window `W = [window_started_at, now]`) | Params kept | Params dropped |
|------|-------------------------------------------------------|-------------|----------------|
| `unanswered_overdue` | `count(reviews: response_text IS NULL AND first_seen_at IN W, scope) >= min_count` | `min_count` (default 1) | `hours` |
| `fresh_negative` | `count(reviews: rating <= max_rating AND first_seen_at IN W, scope) >= min_count` | `max_rating` (2), `min_count` (1) | `window_hours` |
| `rating_drop` | per org in scope, `rating_now - rating_at(window_started_at) <= threshold`; top-N | `threshold` (<0), `top` | — |
| `escalated` | `count(reviews: status == escalated, scope) >= min_count` (window ignored) | `min_count` (1) | — |
| `aspect_spike` | aspect mentions in `W` `>= min_recent` AND `> mentions in [window_started_at - period_days, window_started_at]`; top-N | `min_recent` (3), `top` | — |

**Rationale**: The spec fixes the window as replacing the built-in windows (FR-011). `escalated`
has no status timestamp so it stays a current-state count (FR-015, accepted re-latch). `rating_drop`
reuses `_earliest_snapshot_ratings`-style baseline but anchored at `window_started_at` instead of
the page period start. `aspect_spike`'s baseline is the immediately-preceding equal-length window.

**Alternatives considered**: Keeping per-type hour windows AND-ed with the period window — rejected
by the design decision "Заменяет встроенные окна".

## R6 — Snapshot storage for the block & history

**Decision**: New `attention_events` table stores one row per emitted item at fire time
(`rule_id`, `fired_at`, `type`, `severity`, `title`, `subtitle`, `value`, `link`). The
`/overview` block reads events belonging to **currently-latched** rules; the history view reads
all events for a rule. A firing can insert several rows (e.g. `rating_drop` top-N).

**Rationale**: The user chose "latched + history" (brainstorm). Snapshotting the display fields
means the block never recomputes (FR-018, FR-021, SC-001). One table serves both the live block
(join to latched rules) and history (FR-023). `ON DELETE CASCADE` on `rule_id` gives FR-024.

**Block query**: `SELECT events WHERE rule.is_enabled AND rule.latched_at IS NOT NULL AND
event.fired_at = rule.latched_at` (events of the current firing), ordered in Python by severity
then `abs(value)` to preserve existing ordering (FR-020). Disabled rules excluded (edge case).

## R7 — `period_days` type & default

**Decision**: `period_days INTEGER NOT NULL DEFAULT 1`, validated `>= 1` in the Pydantic
create/update schemas. Migration backfills existing rows to `1`. Seed defaults
(`DEFAULT_RULES`) get `period_days` too.

**Rationale**: Spec fixes whole-day granularity, min 1, default 1 (FR-001, FR-003, Assumptions).

## R8 — Timestamp columns

**Decision**: `window_started_at TIMESTAMPTZ NOT NULL` (default `now()` on insert),
`latched_at TIMESTAMPTZ NULL`, `attention_events.fired_at TIMESTAMPTZ NOT NULL` — all
`DateTime(timezone=True)` in the ORM, consistent with `created_at`/`scrape_runs`.

**Rationale**: Sweep compares against `datetime.now(timezone.utc)`; tz-aware storage avoids the
naive/aware mismatch seen elsewhere (`_dt_param`). SQLite tests tolerate tz-aware datetimes.

## R9 — Overview payload compatibility

**Decision**: The `attention` block keeps its existing JSON item shape
(`type`, `title`, `subtitle`, `value`, `link`, `severity`) so `attention-list.tsx` renders
unchanged. `DashboardService._attention(...)` is replaced by a read from `AttentionEvaluator`
(or a small `attention_events` query helper) that returns the same list-of-dicts; the arguments
`(orgs, platform, snaps, now, aspect_rows, scope)` are dropped since the block no longer depends
on page filters.

**Rationale**: Minimize frontend churn; the contract that changes is *where the data comes from*,
not its shape. `test_dashboard_overview.py`'s other blocks are untouched.

## Open questions

None — all resolved during brainstorming and captured in the spec Assumptions.
