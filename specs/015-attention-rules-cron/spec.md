# Feature Specification: Attention Rules Cron Model

**Feature Branch**: `015-attention-rules-cron`

**Created**: 2026-07-21

**Status**: Draft

**Input**: User description: "Крон-модель для attention-правил блока «Требуют внимания» на /overview. Правила становятся stateful (period_days, window_started_at, latched_at), крон-обходчик каждые 30 минут делает sweep, окно [window_started_at, now] заменяет встроенные окна типов, история срабатываний, restart-эндпоинт, блок читает latched-события и игнорирует фильтры страницы."

## Overview

Today the «Требуют внимания за последние 24 часа» block on `/overview` is computed **live** on every page load: for each enabled attention rule the dashboard runs COUNT queries over reviews and shows any rule whose condition currently holds. Nothing is remembered between requests — a triggered event and a quiet moment look identical the instant the underlying data changes, and the operator has no notion of "I have already seen this, don't show it again for a while."

This feature makes attention rules **stateful and cron-driven**. Each rule gains a trigger period (in days). A background sweep runs every 30 minutes, evaluates each enabled rule over the window since its current period started, and — when a rule's condition is met — **latches** it: the rule fires once, is recorded in a history log, and is not re-evaluated until its period elapses (auto-rollover) or an operator manually restarts it. The `/overview` block stops computing anything live; it simply renders the currently-latched rules from stored snapshots. Operators get a clear "fired / waiting" status per rule, a restart button, and a per-rule history of past firings.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Latched attention feed driven by a background sweep (Priority: P1)

As an operator watching `/overview`, I want the attention block to show events that a background process has already detected and "locked in", so that a real problem stays visible until I have had a chance to act on it, instead of flickering in and out as the raw data shifts.

**Why this priority**: This is the core behavioral change and the reason the feature exists. Without it, nothing else (period, restart, history) has meaning.

**Independent Test**: Configure a rule with a period, create data that satisfies its condition, run the sweep, and confirm the block on `/overview` shows the fired event from stored state (no live recomputation). Confirm the same event keeps showing on subsequent loads without re-querying reviews.

**Acceptance Scenarios**:

1. **Given** an enabled rule whose condition is met within its current period window, **When** the sweep runs, **Then** the rule is marked as fired (latched), a history entry with the event snapshot (title/subtitle/value/link/type/severity) is recorded, and the event appears in the `/overview` block.
2. **Given** a rule that has already fired this period, **When** the sweep runs again before the period elapses, **Then** the rule is not re-evaluated and no new history entry is created.
3. **Given** a rule whose condition is NOT met within its window, **When** the sweep runs, **Then** the rule does not fire and nothing appears for it in the block.
4. **Given** one or more latched rules, **When** an operator opens `/overview` with any combination of page filters (period, platform, organizations), **Then** the block shows all latched rules according to each rule's own scope and ignores the page filters.

---

### User Story 2 - Period, auto-rollover, and manual restart (Priority: P1)

As an operator, I want each rule to have a trigger period in days and to reset itself when the period elapses, and I want to be able to manually restart a rule so it starts watching again immediately, so that I control how often the same kind of alert can re-appear.

**Why this priority**: The period and restart are what make a "latched" event eventually clear and re-arm; without them a fired rule would either never recur or recur uncontrollably.

**Independent Test**: Fire a rule, advance time past its period, run the sweep, and confirm it re-arms and can fire again. Separately, fire a rule, invoke restart, and confirm it re-arms and re-evaluates immediately.

**Acceptance Scenarios**:

1. **Given** a fired rule whose period has elapsed (now ≥ window start + period), **When** the sweep runs, **Then** a new period begins (window start = now), the latch is cleared, and the rule is evaluated again in the new window.
2. **Given** a rule that never fired and whose period has elapsed, **When** the sweep runs, **Then** its window also rolls forward to a new period (the window does not grow without bound).
3. **Given** any rule, **When** an operator restarts it, **Then** its window start is set to now, its latch is cleared, it is re-evaluated immediately, and the operator sees the updated state (fired or waiting) and any freshly created events without waiting for the next sweep.
4. **Given** a rule with period P and last-corroborated fire time, **When** the operator views the rule, **Then** they can see whether it is currently fired or waiting and (when fired) roughly when the current period ends.

---

### User Story 3 - Per-rule firing history (Priority: P2)

As an operator, I want to see the history of when each rule fired and what it reported, so that I can review recurring problems over time rather than only the current state.

**Why this priority**: Valuable for auditing and trend awareness, but the feed and lifecycle (P1) deliver the primary value on their own.

**Independent Test**: Fire a rule across several periods (advancing time / restarting between firings) and confirm each firing is listed in the rule's history with its timestamp and event snapshot.

**Acceptance Scenarios**:

1. **Given** a rule that has fired multiple times across periods, **When** an operator opens the rule's history, **Then** they see one history section per firing with the fire time and the event(s) reported.
2. **Given** a rule that has never fired, **When** an operator opens its history, **Then** they see an explicit empty state.

---

### User Story 4 - Period field in rule management (Priority: P2)

As an operator managing rules on `/attention-rules`, I want to set and edit the trigger period (in days) when creating or editing a rule, so that each rule's cadence matches its urgency.

**Why this priority**: Needed to configure the feature, but existing rules can run on a sensible default period, so it is not strictly blocking for P1.

**Acceptance Scenarios**:

1. **Given** the rule create/edit form, **When** an operator sets a period in days, **Then** the value is validated (whole number ≥ 1) and persisted with the rule.
2. **Given** an existing rule without an explicit period, **When** the feature is deployed, **Then** the rule receives a sensible default period and continues to function.

---

### Edge Cases

- **Disabled rule**: A rule with `is_enabled = false` is skipped by the sweep entirely, and any of its previously-latched events are not shown in the block. Re-enabling starts a fresh window.
- **Rule deleted while latched**: History entries are removed with the rule (cascade); the block no longer shows it.
- **Scope no longer matches any organization** (e.g., all scoped orgs removed): the rule evaluates to "condition not met" and simply does not fire — no error.
- **Escalated type over a window**: The "escalated" status has no timestamp in the data, so the window does not apply — the rule counts currently-escalated reviews in scope. The same old escalated review can therefore re-latch the rule in each new period until the status is cleared (accepted behavior).
- **Sweep overlap**: If a sweep is still running when the next 30-minute tick arrives, the two must not double-process the same rule (no duplicate history entries for one firing).
- **Multiple items from one firing**: A single firing of a rule (e.g., a rating-drop rule reporting its top-N organizations) may produce several event snapshots; all are recorded and displayed as belonging to that firing.
- **Clock/period boundary**: A rule whose period has elapsed by only a few minutes when the sweep runs rolls over at that sweep; the new window starts at the sweep time (not the exact theoretical boundary).
- **Empty feed**: When no rule is latched, the block shows its existing empty state ("Нет событий, требующих внимания").

## Requirements *(mandatory)*

### Functional Requirements

#### Rule state & configuration

- **FR-001**: Each attention rule MUST have a trigger period expressed in whole days, validated as ≥ 1, settable on create and edit.
- **FR-002**: Each attention rule MUST track the start time of its current period ("window start") and whether it has fired in the current period ("latched", with the fire time).
- **FR-003**: Existing rules MUST receive a sensible default period on migration and continue to function without manual reconfiguration.

#### Background sweep & lifecycle

- **FR-004**: A background process MUST evaluate all enabled rules every 30 minutes.
- **FR-005**: For each rule, the sweep MUST first roll the period forward when the current period has elapsed (now ≥ window start + period): set a new window start of "now" and clear the latch. This applies whether or not the rule had fired.
- **FR-006**: After any rollover, if the rule is not latched, the sweep MUST evaluate the rule's condition over the window [window start, now]. If the condition is met, the rule MUST be latched (fire time = now) and its event snapshot(s) recorded in history.
- **FR-007**: A rule that is already latched MUST NOT be re-evaluated until its period elapses or it is restarted; no duplicate history entry may be created for an already-latched rule.
- **FR-008**: The sweep MUST skip rules that are disabled.
- **FR-009**: The sweep MUST be resilient: a failure evaluating one rule MUST NOT prevent other rules from being evaluated, and concurrent/overlapping sweeps MUST NOT double-process a rule.
- **FR-010**: The background sweep MUST be controllable by a configuration flag and MUST be disabled in the automated test environment by default.

#### Evaluation window semantics (replaces built-in per-type windows)

- **FR-011**: The evaluation window for every rule type MUST be [window start, now]; the previously hard-coded per-type windows (e.g., 2h / 24h / 7d) no longer apply.
- **FR-012**: "Unanswered overdue" MUST fire when the count of reviews without a business response, first observed within the window and within the rule's scope, is ≥ a configurable minimum count.
- **FR-013**: "Fresh negative" MUST fire when the count of reviews with rating ≤ a configurable maximum, first observed within the window and within scope, is ≥ a configurable minimum count.
- **FR-014**: "Rating drop" MUST fire when, for at least one organization in scope, the platform rating dropped by at least the configured threshold between the window start and now (based on rating snapshots), reporting up to the configured top-N organizations.
- **FR-015**: "Escalated" MUST fire when the count of currently-escalated reviews within scope is ≥ a configurable minimum count. The window does not filter this type (no status timestamp exists).
- **FR-016**: "Aspect spike" MUST fire when a problem aspect's mention count within the window is ≥ a configurable minimum AND greater than its mention count in the immediately-preceding window of equal length ([window start − period, window start]), reporting up to the configured top-N aspects.
- **FR-017**: Obsolete purely-time parameters (the per-type hour windows) MUST be removed from rule configuration; scope, severity, and the type-specific thresholds above are retained.

#### Overview block behavior

- **FR-018**: The `/overview` attention block MUST render only currently-latched rules from stored event snapshots and MUST NOT recompute rule conditions on page load.
- **FR-019**: The block MUST ignore page filters (period, platform, organizations) and show all latched rules according to each rule's own scope.
- **FR-020**: The block MUST preserve its existing ordering (by severity, then by magnitude of value) and its empty state when nothing is latched.
- **FR-021**: Each displayed event MUST use the snapshot captured at fire time (title, subtitle, value, link, type, severity) rather than a live recomputation.

#### Restart & history

- **FR-022**: The system MUST provide an admin-only action to restart a rule: set its window start to now, clear its latch, re-evaluate it immediately, and return the updated rule state plus any freshly created events.
- **FR-023**: The system MUST retain a per-rule history of firings (each with fire time and the event snapshot(s)) and expose it for viewing per rule.
- **FR-024**: Deleting a rule MUST remove its history.

#### Management UI

- **FR-025**: The `/attention-rules` page MUST let operators set the period (in days) on create/edit, show each rule's current status (fired / waiting, with an indication of when the current period ends), offer a restart control, and provide access to the rule's firing history.
- **FR-026**: All rule mutations, restart, and the sweep MUST remain consistent with the project's read-only constraint — no data is published, edited, or deleted on any review platform.

### Key Entities *(include if feature involves data)*

- **Attention Rule** (extended): a configured watch with a type, severity, scope (global / company / specific organizations), type-specific thresholds, and now a **trigger period (days)**, a **current window start**, and a **latch state (fired time or none)**.
- **Attention Event** (new): a recorded firing snapshot belonging to a rule — fire time, event type, severity, and the display fields (title, subtitle, value, link). One firing may create several events. Serves both the live block (events of currently-latched rules) and the history view. Removed when its rule is deleted.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Opening `/overview` performs no per-review counting for the attention block — the block's data comes entirely from stored state, so its contribution to page load time is constant regardless of review volume or organization count.
- **SC-002**: A rule that meets its condition is reflected in the block within one sweep interval (≤ 30 minutes) of the condition first becoming true.
- **SC-003**: Once fired, a rule remains visible and is not re-triggered for the full duration of its configured period (barring a manual restart), with exactly one firing recorded per period.
- **SC-004**: After a manual restart, the operator sees the rule's updated state and any new events immediately (without waiting for the next sweep).
- **SC-005**: For every rule that has ever fired, an operator can retrieve a complete chronological history of its firings.
- **SC-006**: No attention-related action results in any write to an external review platform (read-only invariant upheld).

## Assumptions

- **Sweep cadence is fixed at 30 minutes** and runs in the existing in-process scheduler; it is not independently configurable per rule beyond the period.
- **Period granularity is whole days, minimum 1.** Sub-day periods are out of scope. (Consequently, short-lived signals such as fresh negatives stay latched for at least one day.)
- **Default period for existing/seeded rules is 1 day.**
- **The window rollover anchors to sweep time**, not to an exact theoretical period boundary; drift of up to one sweep interval is acceptable.
- **Restart is an operator (admin) action**, consistent with existing admin-only rule mutations.
- **The `/overview` block no longer reflects page filters for attention** — this is an intentional UX change; other overview blocks are unaffected.
- **Escalated type intentionally ignores the window** because the underlying status has no timestamp; re-latching each period until the status clears is acceptable.
- **History retention is unbounded for now** (rule firings are low-volume); a retention policy can be added later if needed.
- **Existing scope semantics are unchanged** (global / company / specific organizations); only the page-filter intersection is dropped.
