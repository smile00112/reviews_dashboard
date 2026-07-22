# Phase 1 Data Model: Attention Rules Cron Model

## Entity: AttentionRule (extended)

Existing table `attention_rules` (migration 0015). **Additive** columns only.

| Column | Type | Null | Default | Notes |
|--------|------|------|---------|-------|
| *(existing)* id, rule_type, name, is_enabled, severity, params, scope_type, company_id, organization_ids, created_at, updated_at | — | — | — | Unchanged |
| `period_days` | INTEGER | NOT NULL | `1` | Trigger period in whole days; validated `>= 1`. Migration backfills existing rows to 1. |
| `window_started_at` | TIMESTAMPTZ | NOT NULL | `now()` | Start of the current period ("время начала работы"). Set on insert, on rollover, and on restart. Migration backfills to `now()` (or `created_at`). |
| `latched_at` | TIMESTAMPTZ | NULL | `NULL` | Fire time of the current period. `NULL` = not fired this period. |

**Derived state** (not stored): `is_latched := latched_at IS NOT NULL`;
`period_ends_at := window_started_at + period_days` (for UI "waiting until").

### `params` per type — reworked

Purely-time params are removed; type thresholds are kept and `min_count` is added where a count
gate applies. (Pydantic `PARAM_MODELS`, `extra="forbid"`.)

| Type | params (after) | Removed |
|------|----------------|---------|
| `unanswered_overdue` | `min_count: int = 1 (ge=1)` | `hours` |
| `fresh_negative` | `max_rating: int = 2 (ge=1, le=4)`, `min_count: int = 1 (ge=1)` | `window_hours` |
| `escalated` | `min_count: int = 1 (ge=1)` | — (was empty) |
| `rating_drop` | `threshold: float = -0.2 (lt=0)`, `top: int = 3 (ge=1, le=10)` | — |
| `aspect_spike` | `min_recent: int = 3 (ge=1)`, `top: int = 3 (ge=1, le=10)` | — |

### Validation rules

- `period_days` whole number `>= 1` (422 otherwise), on create and update.
- Scope validation unchanged (`company` needs `company_id`; `organizations` needs a non-empty,
  existing-id list).
- `params` validated by type via `PARAM_MODELS`; unknown key → 422.

## Entity: AttentionEvent (new)

New table `attention_events` — one row per emitted item at fire time (snapshot).

| Column | Type | Null | Notes |
|--------|------|------|-------|
| `id` | UUID (pk) | NOT NULL | `uuid4` |
| `rule_id` | UUID (fk → attention_rules.id, ON DELETE CASCADE) | NOT NULL | History removed with the rule (FR-024). |
| `fired_at` | TIMESTAMPTZ | NOT NULL | Equals the rule's `latched_at` for that firing (a firing = one `fired_at` shared by its rows). |
| `type` | attention_rule_type_enum (string) | NOT NULL | Snapshot of the emitting rule type (item `type`). |
| `severity` | attention_severity_enum (string) | NOT NULL | Snapshot of severity at fire time. |
| `title` | String(400) | NOT NULL | Rendered title snapshot. |
| `subtitle` | String(400) | NULL | Rendered subtitle snapshot. |
| `value` | Float | NOT NULL | Numeric magnitude (counts, or negative delta for rating_drop). |
| `link` | String(400) | NOT NULL | Deep link snapshot (`/reviews`, `/organizations/{id}`, …). |
| `created_at` | TIMESTAMPTZ | NOT NULL | `now()` server default. |

**Indexes**:
- `ix_attention_events_rule_fired` on `(rule_id, fired_at DESC)` — history listing + current-firing lookup.

**Relationships**: `AttentionRule 1—* AttentionEvent` (cascade delete). No relationship to
`Review` (snapshots are self-contained; a deleted/changed review must not alter recorded history).

## Rule lifecycle state machine

States are derived from columns; transitions happen only in `AttentionEvaluator`.

```text
            create / enable / restart
                   │  window_started_at = now
                   │  latched_at = NULL
                   ▼
             ┌───────────┐   condition met in [window_started_at, now]
             │  ARMED    │ ───────────────────────────────────────────┐
             │ latched=∅ │                                             │
             └───────────┘                                             ▼
                   ▲                                             ┌───────────┐
   now ≥ window +  │                                             │  LATCHED  │
   period_days     │   now ≥ window_started_at + period_days     │ latched=t │
   (rollover:      └─────────────────────────────────────────────│           │
    window=now,                                                   └───────────┘
    latched=NULL)                                                  (skipped by
                                                                    sweep until
                                                                    rollover)
```

Sweep step per enabled rule (single transaction, row-locked):

```text
if now >= window_started_at + period_days:      # FR-005 rollover (fired or not)
    window_started_at = now
    latched_at = NULL
if latched_at is None:                           # FR-006 evaluate only if armed
    items = evaluate_rule(rule, window_started_at, now)   # FR-011..FR-016
    if items:
        latched_at = now                         # FR-006 latch
        insert attention_events(rule_id, fired_at=now, <snapshot each item>)
# disabled rules never enter the sweep (FR-008)
```

Restart (admin action, synchronous — FR-022):

```text
window_started_at = now
latched_at = NULL
run the sweep step above for this one rule immediately
return (updated rule state, events created now)
```

## Overview read path (replaces live `_attention`)

```text
block_items =
  SELECT e.* FROM attention_events e JOIN attention_rules r ON r.id = e.rule_id
  WHERE r.is_enabled = true
    AND r.latched_at IS NOT NULL
    AND e.fired_at = r.latched_at        # only the current firing's snapshots
  # page filters (period/platform/org_ids/company_id) intentionally NOT applied (FR-019)
# ordered in Python: severity rank (urgent<warn<info), then -abs(value)  (FR-020)
```

Empty result → existing empty state (FR-020 / edge case "Empty feed").

## Migration `0023_attention_events_and_lifecycle`

1. `ALTER TABLE attention_rules ADD COLUMN period_days INTEGER NOT NULL DEFAULT 1`.
2. `ADD COLUMN window_started_at TIMESTAMPTZ NOT NULL DEFAULT now()` (backfill = now()/created_at).
3. `ADD COLUMN latched_at TIMESTAMPTZ NULL`.
4. `CREATE TABLE attention_events (...)` with FK cascade + index.
5. Data backfill for existing rows: `period_days=1`, `window_started_at=created_at` (or now),
   `latched_at=NULL` (they re-arm on the first sweep).
6. Downgrade drops the table and the three columns.

Follows the established pattern: raw column type `scrape_mode`-style enums reuse existing PG enum
types (`attention_rule_type_enum`, `attention_severity_enum`) for `attention_events.type/severity`;
JSON columns keep the `JSON().with_variant(JSONB, "postgresql")` variant elsewhere (not needed
here — event columns are scalar).
