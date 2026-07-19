# Implementation Plan: Dashboard Overview Performance

**Branch**: `012-dashboard-overview-perf` | **Date**: 2026-07-19 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/012-dashboard-overview-perf/spec.md`

## Summary

`DashboardService.overview` currently materializes **every** `Review` row for the selected organizations as full ORM objects (`base.all()`, all-time, including `review_text` and `problems` JSONB) and computes all aggregates in Python; a platform-filtered request performs a second full scan for platform cards. At current volume this costs ~5 s per request. The rewrite pushes count/distribution work into a fixed number of SQL aggregate queries, narrows the remaining per-review loads to only the columns and time windows they need, and adds supporting indexes. The JSON payload is bit-identical for the same data (existing test suites are the behavioral contract); target is <300 ms.

## Technical Context

**Language/Version**: Python 3.11 (FastAPI backend, `apps/api`)

**Primary Dependencies**: FastAPI, SQLAlchemy 2.x ORM, Alembic, pydantic v2

**Storage**: PostgreSQL 16 (production), SQLite (pytest backend via `tests/conftest.py`)

**Testing**: pytest (`apps/api`); behavioral contract = `test_dashboard_overview.py`, `test_dashboard_attention_rules.py`, query budget = `test_query_counts.py::test_overview_query_count_does_not_scale_with_orgs`

**Target Platform**: Linux server (Docker Compose), Windows dev host

**Project Type**: web-service (monorepo `apps/api` + `apps/web`; this feature touches only `apps/api`)

**Performance Goals**: overview endpoint <300 ms at current production volume (p95 <500 ms); must hold at 10× review volume

**Constraints**: identical response payload (values, ordering, rounding); identical behavior on PostgreSQL and SQLite; no schema changes beyond additive indexes; no new services/caches

**Scale/Scope**: ~tens of organizations, 10⁴–10⁵ review rows; one service file rewrite + one Alembic migration + regression tests

## Constitution Check

*GATE: evaluated against constitution v1.4.0 — PASS (pre- and post-design).*

| Principle | Status | Note |
|---|---|---|
| I. MVP Scope Discipline | PASS | Performance work on an existing in-scope dashboard; no new features. |
| II. Read-Only Collection | PASS | Read path only; no writes to reviews. |
| III. Critical-Path Testing | PASS | Existing overview/attention suites stay green unchanged; query-count guard already exists and is extended. No dedup/persistence logic touched. |
| IV. Scraper Reliability | PASS | Scrapers untouched. |
| V. Simplicity (YAGNI) | PASS | No cache layer, no materialized/history table, no new dependency — plain SQL aggregates + indexes. Precomputed aggregate table explicitly rejected (see research.md R5). |
| VI. Deterministic Local Analytics | PASS | `summarize()` inputs/outputs unchanged; sentiment percents recomputed from grouped counts with the identical rounding formula; no external calls. |
| VII. Admin Panel Security | PASS | Endpoint auth untouched (`get_current_user` stays). |
| VIII. Multi-Provider Collection | PASS | No provider/dedup changes. |

No Complexity Tracking entries required.

## Project Structure

### Documentation (this feature)

```text
specs/012-dashboard-overview-perf/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output (index additions + query shapes)
├── quickstart.md        # Phase 1 output (validation guide)
├── contracts/
│   └── overview-unchanged.md   # payload-identity + query-budget contract
└── tasks.md             # Phase 2 output (/speckit-tasks)
```

### Source Code (repository root)

```text
apps/api/
├── app/
│   ├── services/
│   │   └── dashboard_service.py   # rewrite of overview() internals (only file with logic changes)
│   └── models/
│       └── review.py              # additive Index() entries in __table_args__
├── alembic/versions/
│   └── 0017_dashboard_overview_indexes.py   # new additive migration
└── tests/
    ├── test_dashboard_overview.py           # unchanged — contract
    ├── test_dashboard_attention_rules.py    # unchanged — contract
    └── test_query_counts.py                 # extended: overview must not scale with review count either
```

**Structure Decision**: single-file service rewrite inside the existing `apps/api` layering (api → services → models); no web changes (`apps/web` payload consumption is untouched).

## Design

### Query plan (replaces the two full scans)

Fixed query budget per request, independent of org/review count (attention rules add O(enabled rules) tiny COUNTs — bounded by operator configuration, not data volume). Profiling on the real dataset (52k reviews / 604 organizations) collapsed the originally planned per-block aggregates into a single grouped scan, because each extra full-table aggregate cost 30–100 ms on its own:

| # | Purpose | Shape |
|---|---|---|
| C1 | **The cube** — every counter and distribution | one `GROUP BY (platform, rating, sentiment)` scan of the scoped reviews (≤ 60 result rows). Per group: all-time `total`, period `count`, `new_today`, `fresh_negatives_2h`, `unanswered_total`, `overdue_24h`, `unanswered_delta_24h`, `MIN(first_seen_at)`, plus period response `count` / `SUM(delay)` / within-SLA count. Time windows are `CASE` conditionals, not separate scans. Folded in Python into header, KPI hero, rating distribution, sentiment split, platform cards, and kpi_strip averages |
| C2 | Response-time percentiles (kpi_strip) | `percentile_cont(0.5 / 0.95)` over the delay expression on PostgreSQL — same linear-interpolation definition as `statistics.median` / `_percentile`; SQLite (tests) lacks the function and falls back to loading the delay values |
| C3 | Unanswered per org (worst locations) | `GROUP BY organization_id WHERE response_text IS NULL` |
| C4 | Aspects (trending + spikes) | narrow load: `(organization_id, review_date, problems, sentiment)` `WHERE review_date >= now-14d AND problems IS NOT NULL`; Python bucketing unchanged |
| C5× | Attention rule counters | per enabled count-type rule (`unanswered_overdue`, `fresh_negative`, `escalated`): one scoped `COUNT`; `aspect_spike` consumes C4; `rating_drop` consumes orgs+snapshots (already batched) |

The response delay itself is computed in SQL (`extract(epoch …)` on PostgreSQL, `julianday()` on SQLite) so no timestamps are shipped per row — the earlier version transferred 50k datetime pairs and cost 315 ms alone.

**Org scoping shortcut**: when neither `org_ids` nor `company_id` is given, every organization is selected, so the review queries omit the `organization_id IN (…)` clause entirely — a 604-element UUID list cost more than the scan it guarded.

Python-side logic that stays (deliberately, to preserve exact ordering/rounding): `_worst_locations` iteration over `orgs` (unanswered counts come from C3), attention item sorting, all `round()` calls, and the `summarize`-equivalent percent formula over the cube's sentiment counts.

### Timezone handling (PG ↔ SQLite)

All cutoffs are computed as aware-UTC datetimes. On the SQLite test backend, bind parameters are normalized to naive UTC (tzinfo stripped) via one helper so string-typed comparisons behave like the current `_aware()` Python logic; PostgreSQL keeps aware binds (`timestamptz`). See research.md R2.

### Indexes (migration 0017, additive)

- `ix_reviews_org_unanswered` — partial: `(organization_id) WHERE response_text IS NULL` (A4, unanswered counters).
- `ix_reviews_org_platform_first_seen` — `(organization_id, platform, first_seen_at)` (platform-filtered period scans).
- Existing `ix_reviews_org_first_seen`, `ix_reviews_org_review_date`, `ix_reviews_org_platform` (feature 010) already cover the rest.

Declared in `Review.__table_args__` with `postgresql_where`/`sqlite_where` so `create_all` test schema matches.

## Complexity Tracking

No constitution violations — table intentionally empty.
