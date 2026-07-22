# Implementation Plan: Attention Rules Cron Model

**Branch**: `015-attention-rules-cron` | **Date**: 2026-07-21 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/015-attention-rules-cron/spec.md`

## Summary

Turn the `/overview` «Требуют внимания» block from a live, per-request computation into a
**stateful, cron-driven engine**. Each `attention_rules` row gains a trigger period
(`period_days`), a current-period start (`window_started_at`), and a latch (`latched_at`).
An APScheduler sweep runs every 30 minutes: it rolls a rule's period forward when elapsed
(new `window_started_at = now`, latch cleared), then — if not latched — evaluates the rule's
condition over the window `[window_started_at, now]` (which **replaces** the old per-type
2h/24h/7d windows) and, on a hit, latches it and appends snapshot rows to a new
`attention_events` table. The rule-condition logic moves out of `DashboardService._attention`
into a reusable `AttentionEvaluator`, shared by the sweep and a new admin-only
`POST /api/attention-rules/{id}/restart` endpoint (window reset + synchronous re-evaluation).
`DashboardService.overview` stops computing the block and instead reads currently-latched
events, ignoring page filters. UI adds a period field, fired/waiting status, a restart button,
and per-rule history.

## Technical Context

**Language/Version**: Python 3.11 (FastAPI backend), TypeScript / Next.js App Router (web)

**Primary Dependencies**: FastAPI, SQLAlchemy, Alembic, APScheduler (`BackgroundScheduler`,
already in-process via `JobScheduler`), Pydantic v2; Next.js 14 server/client components

**Storage**: PostgreSQL 16 (prod), SQLite (tests) — via `JSON().with_variant(JSONB, "postgresql")`
pattern for JSON columns; `DateTime(timezone=True)` for timestamps

**Testing**: pytest (api, scheduler forced off via `conftest.py`), Playwright E2E (web)

**Target Platform**: Linux server (Docker Compose), internal read-only dashboard

**Project Type**: Web application (monorepo `apps/api` + `apps/web`)

**Performance Goals**: `/overview` attention block cost O(1) in review/org volume (reads stored
events only); sweep processes tens of rules over tens of organizations every 30 min, well within
one scheduler tick

**Constraints**: Read-only (no writes to review platforms); deterministic local evaluation (no
LLM/external calls); additive ORM changes only; dedup contract (`build_review_hash`,
`uq_review_org_hash`) untouched; scheduler must stay off in tests

**Scale/Scope**: ~tens of organizations, a handful of attention rules, low firing volume

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. MVP Scope Discipline | PASS | Extends an existing in-scope feature (attention block); no excluded capability (no LLM, no Celery/queue — reuses the in-process APScheduler; no new provider). |
| II. Read-Only Review Collection | PASS | Sweep and restart only read reviews/snapshots and write to app-owned tables (`attention_rules`, `attention_events`). No platform writes. |
| III. Critical-Path Testing | PASS | New tests for lifecycle (latch/rollover/restart), per-type evaluation semantics, sweep idempotency, and the overview-reads-stored-state contract. Existing `test_dashboard_attention_rules.py` / `test_attention_rules_api.py` adapted. |
| IV. Scraper Reliability | PASS (N/A) | No scraper change; sweep is resilient per-rule (one rule's error does not abort the sweep). |
| V. Simplicity (YAGNI) | PASS | Reuses the existing `JobScheduler` + lifespan gate (`jobs_scheduler_enabled`) instead of a new scheduler/flag; one new table, three new columns. No queue. |
| VI. Deterministic Local Analytics | PASS | Evaluation stays rule-based and local; no external inference. |
| VII. Admin Panel Security | PASS | Restart is admin-only (`require_admin`), matching existing rule mutations; list/read stays `get_current_user`. |
| VIII. Multi-Provider Collection | PASS (N/A) | No collection path change; evaluation is provider-agnostic over stored reviews/snapshots. |

**Gate result: PASS** — no violations; Complexity Tracking not required.

## Project Structure

### Documentation (this feature)

```text
specs/015-attention-rules-cron/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output (REST + internal interfaces)
│   ├── attention-rules-api.md
│   └── evaluator-interface.md
├── checklists/
│   └── requirements.md   # from /speckit-specify
└── tasks.md             # /speckit-tasks (later)
```

### Source Code (repository root)

```text
apps/api/
├── app/
│   ├── models/
│   │   ├── attention_rule.py        # +period_days, window_started_at, latched_at
│   │   └── attention_event.py       # NEW: firing snapshot rows
│   ├── schemas/
│   │   └── attention_rule.py        # +period_days on Create/Update/Response;
│   │                                #  rework param models (drop hours/window_hours,
│   │                                #  add min_count); +Event + Restart response schemas
│   ├── services/
│   │   ├── attention_evaluator.py   # NEW: condition logic (moved from DashboardService)
│   │   │                            #  + sweep() + restart() + rollover/latch
│   │   ├── attention_rule_service.py# +period_days handling, seed default period
│   │   ├── job_scheduler.py         # register 30-min sweep trigger in sync_all()
│   │   └── dashboard_service.py     # _attention -> read latched events; delete live calc
│   ├── api/
│   │   └── attention_rules.py       # +POST /{id}/restart; +history/events endpoint
│   └── main.py                      # (no change; sweep rides existing lifespan gate)
├── alembic/versions/
│   └── 0023_attention_events_and_lifecycle.py   # NEW migration
└── tests/
    ├── test_attention_rules_api.py           # adapt (period_days, restart, history)
    ├── test_dashboard_attention_rules.py     # adapt (reads stored events)
    ├── test_attention_evaluator.py           # NEW (lifecycle + per-type semantics)
    └── test_attention_sweep.py               # NEW (rollover, idempotency, disabled skip)

apps/web/
├── app/(dashboard)/
│   ├── overview/page.tsx                      # attention now from stored events
│   └── attention-rules/page.tsx              # +period field, status, restart, history
├── components/dashboard/
│   └── attention-list.tsx                    # render event snapshots (mostly unchanged)
├── components/attention-rules/               # rule form/status/history client components
└── lib/
    ├── api.ts / types.ts                     # +period_days, event, restart types
```

**Structure Decision**: Web-application monorepo (Option 2). All backend changes live under
`apps/api/app` following the strict `api → services → models/schemas` layering; the reusable
evaluation logic is a new **service** (`AttentionEvaluator`) so both the scheduler and the
restart endpoint call the same code (no logic in the router, none left in `DashboardService`
beyond reading stored events). Frontend changes stay within existing App Router pages and the
`lib/api.ts` wrapper.

## Phase 0 — Research

See [research.md](./research.md). Key decisions: reuse `JobScheduler` (no new scheduler/flag);
static APScheduler cron entry `*/30 * * * *` registered in `sync_all`; `max_instances=1` job
default already prevents overlapping sweeps; window rollover anchored to sweep time; per-type
semantics table finalized; timestamps stored `DateTime(timezone=True)`.

## Phase 1 — Design & Contracts

- [data-model.md](./data-model.md) — `attention_rules` new columns + `attention_events` table,
  validation rules, and the rule lifecycle state machine.
- [contracts/attention-rules-api.md](./contracts/attention-rules-api.md) — REST surface
  (list/create/update/delete unchanged shape + `period_days`; new restart + history/events).
- [contracts/evaluator-interface.md](./contracts/evaluator-interface.md) — `AttentionEvaluator`
  internal interface (`sweep`, `evaluate_rule`, `restart`) and the overview read path.
- [quickstart.md](./quickstart.md) — end-to-end validation scenarios.

## Complexity Tracking

No constitution violations — table intentionally omitted.
