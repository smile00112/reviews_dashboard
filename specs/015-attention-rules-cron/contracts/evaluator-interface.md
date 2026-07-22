# Contract: AttentionEvaluator (internal service interface)

`app/services/attention_evaluator.py`. Constructed with a `Session` (like the other services).
Holds all rule-condition logic (moved out of `DashboardService._attention`) plus the lifecycle
(rollover/latch) and is called by both the scheduler sweep and the restart endpoint. `now` is
injected (default `datetime.now(timezone.utc)`) so tests control time.

## `sweep(now: datetime | None = None) -> int`

Process every **enabled** rule once. Returns the number of rules that fired this sweep.

Per rule (row-locked, single transaction per rule so one failure is isolated — FR-009):

1. **Rollover** (FR-005): if `now >= rule.window_started_at + timedelta(days=rule.period_days)`
   → `rule.window_started_at = now`, `rule.latched_at = None`.
2. **Evaluate if armed** (FR-006): if `rule.latched_at is None`, call
   `evaluate_rule(rule, rule.window_started_at, now)`. If it returns a non-empty item list →
   `rule.latched_at = now` and insert one `AttentionEvent` per item (snapshotting
   `type/severity/title/subtitle/value/link`, `fired_at=now`).
3. Latched, un-rolled rules are skipped (FR-007) — no re-eval, no duplicate events.
4. Disabled rules are never selected (FR-008).

Errors evaluating one rule are caught, logged, and do not abort the others (FR-009). Commit is
per-rule (or savepoint-wrapped) so partial progress survives.

## `restart(rule_id: UUID, now: datetime | None = None) -> RestartResult | None`

Admin action (FR-022). Returns `None` if the rule does not exist.

1. `rule.window_started_at = now`, `rule.latched_at = None`.
2. Run steps 2 of `sweep` for this single rule synchronously (evaluate + maybe latch + events).
3. Return `RestartResult(rule=<rule>, events=<events created now>)`.

Disabled rule: window reset, no events (or reject — see API contract).

## `evaluate_rule(rule, window_start: datetime, now: datetime) -> list[Item]`

Pure condition evaluation over the window `W = [window_start, now]`. No state mutation. Returns
0..N display items (dicts: `type`, `title`, `subtitle`, `value`, `link`; `severity` attached by
caller from the rule). Dispatch by `rule.rule_type`:

- **unanswered_overdue**: `n = count(Review: response_text IS NULL AND first_seen_at ∈ W,
  scope, platform)`. Emit one item if `n >= min_count`.
- **fresh_negative**: `n = count(Review: rating <= max_rating AND first_seen_at ∈ W, scope,
  platform)`. Emit one item if `n >= min_count`.
- **escalated**: `n = count(Review: status == escalated, scope, platform)` (W ignored — no
  status timestamp, FR-015). Emit one item if `n >= min_count`.
- **rating_drop**: for each org in scope, `delta = rating_now − rating_at(window_start)` using
  the snapshot baseline at `window_start`. Emit up to `top` items where `delta <= threshold`,
  worst first.
- **aspect_spike**: recent = aspect mention counts over `W`; baseline = counts over
  `[window_start − period_days, window_start]`. Emit up to `top` aspects where
  `recent[cat] >= min_recent AND recent[cat] > baseline[cat]`, largest %-change first.

Scope resolution reuses the existing rule-scope logic (global / company / organizations); the
page-filter intersection is dropped (evaluation is per the rule's own scope only). The count and
snapshot-baseline helpers are the current `_scoped_count` / snapshot-rating helpers, relocated.

## `current_block_items() -> list[Item]` (overview read path)

Used by `DashboardService.overview` to fill the `attention` block without recomputation
(FR-018). Query `attention_events` joined to `attention_rules` where the rule is enabled and
latched and `event.fired_at == rule.latched_at`; map each row to the item shape and sort by
severity rank then `-abs(value)` (FR-020). Ignores all page filters (FR-019).

## Types

```text
Item          = { type: str, title: str, subtitle: str|None, value: float,
                  link: str, severity: str }
RestartResult = { rule: AttentionRule, events: list[AttentionEvent] }
```

## Scheduler adapter

`JobScheduler.run_attention_sweep()` opens its own `SessionLocal`, calls
`AttentionEvaluator(db).sweep()`, closes the session. Registered in `JobScheduler.sync_all()`
as cron `*/30 * * * *` (Europe/Moscow), `id="attention-sweep"`, `replace_existing=True`.
Off in tests via the existing `jobs_scheduler_enabled` gate (FR-010).
