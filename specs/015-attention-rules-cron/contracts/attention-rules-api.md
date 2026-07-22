# Contract: Attention Rules REST API

Base: `/api/attention-rules`. Auth: list/read require an authenticated user
(`get_current_user`); all mutations + restart require `admin` (`require_admin`).
Unauthenticated → 401; non-admin on a mutation → 403.

## Changed: rule shape gains lifecycle fields

`AttentionRuleResponse` adds:

```jsonc
{
  // ...existing: id, rule_type, name, is_enabled, severity, params,
  //              scope_type, company_id, organization_ids, created_at, updated_at
  "period_days": 1,                       // integer >= 1
  "window_started_at": "2026-07-21T09:00:00Z",
  "latched_at": "2026-07-21T09:30:00Z",   // null when armed/not fired this period
  "is_latched": true,                     // derived (latched_at != null)
  "period_ends_at": "2026-07-22T09:00:00Z" // derived (window_started_at + period_days)
}
```

`AttentionRuleCreate` / `AttentionRuleUpdate` accept `period_days` (default 1 on create;
optional on update). `params` shapes reworked per data-model (drop `hours`/`window_hours`,
add `min_count`). Unknown param key → 422. `period_days < 1` → 422.

## GET `/api/attention-rules`

Unchanged path; each item now includes the lifecycle fields above.

Optional query `?include=events_current` MAY embed each latched rule's current-firing events
(for the management page status). Default: not embedded.

## POST `/api/attention-rules` — create (admin)

Body: `AttentionRuleCreate` (+`period_days`). 201 → `AttentionRuleResponse`. New rules start
armed: `window_started_at = now`, `latched_at = null`.

## PATCH `/api/attention-rules/{id}` — update (admin)

Body: `AttentionRuleUpdate` (+optional `period_days`). 200 → `AttentionRuleResponse`.
404 if not found. Editing does **not** implicitly restart the window (an explicit restart does);
changing `period_days` takes effect at the next sweep's rollover check.

## DELETE `/api/attention-rules/{id}` — delete (admin)

204. Cascade-deletes the rule's `attention_events` (history). 404 if not found.

## NEW: POST `/api/attention-rules/{id}/restart` — restart (admin)

Resets the rule's window and re-evaluates it immediately (synchronous).

- Effect: `window_started_at = now`, `latched_at = null`, then run the single-rule sweep step
  now; if the condition holds, the rule latches and fresh events are created.
- 200 → `AttentionRuleRestartResponse`:

```jsonc
{
  "rule": { /* AttentionRuleResponse, reflecting post-restart state */ },
  "events": [ /* AttentionEventResponse[] created by this restart, may be empty */ ]
}
```

- 404 if not found.
- Restarting a **disabled** rule: allowed (resets window) but produces no events and stays
  invisible in the block until re-enabled. (Alternatively 409 — implementation MAY reject;
  default is allow-and-no-op-events.)

## NEW: GET `/api/attention-rules/{id}/events` — firing history (auth)

Chronological (newest first) list of the rule's recorded firings.

- 200 → `AttentionEventListResponse`:

```jsonc
{
  "items": [
    {
      "id": "…", "rule_id": "…",
      "fired_at": "2026-07-21T09:30:00Z",
      "type": "fresh_negative", "severity": "urgent",
      "title": "3 новых негативных отзыва (1–2★)",
      "subtitle": "Ночная смена · …",
      "value": 3.0,
      "link": "/reviews?rating=1"
    }
  ]
}
```

- Optional `?limit=N` (default e.g. 50). 404 if the rule does not exist.
- Grouping by `fired_at` (one firing = several rows) is presentational (frontend groups).

## Overview payload (`GET /api/dashboard/overview`) — `attention` block

Item shape **unchanged** (`type`, `severity`, `title`, `subtitle`, `value`, `link`), so
`attention-list.tsx` is untouched in shape. Behavioral change only: items now come from stored
latched events and ignore the page filters (`period`, `platform`, `org_ids`, `company_id`).
Ordering preserved (severity, then magnitude). Empty when nothing latched.
