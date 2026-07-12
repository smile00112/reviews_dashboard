# Implementation Plan: Backend Hardening — Scrape Reliability, Performance, Data Consistency

**Branch**: `010-backend-hardening` | **Date**: 2026-07-12 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/010-backend-hardening/spec.md`

## Summary

Backend-only hardening of `apps/api` fixing 12 audit findings: batch-safe review upsert with exact counters (savepoint + preloaded hash map), truthful parent-run aggregation for `/api/scrape/all`, genuinely-async session login/check (new `pending` session status + BackgroundTasks), challenge re-check with debug artifacts in the operator-auth scraper, N+1 elimination (upsert lookup, dashboard rating-delta/platform-cards, companies branch counts), additive review indexes (migration 0013), uniform `rating >= 1` guard for 2GIS, shared bot-marker module, stdlib logging setup with mandatory warnings on swallowed exceptions, and fail-closed CORS. No frontend changes; no API shape changes — only semantics (202s become truthful, parent status becomes accurate). All decisions locked in [research.md](research.md).

## Technical Context

**Language/Version**: Python 3.11

**Primary Dependencies**: FastAPI, SQLAlchemy 2.x, Alembic, Playwright (sync), pydantic-settings, requests, BeautifulSoup

**Storage**: PostgreSQL 16 (prod, docker compose); SQLite in-memory/file for tests

**Testing**: pytest (`apps/api/tests`), FastAPI TestClient, SQLite backend

**Target Platform**: Linux server (Docker), Windows dev

**Project Type**: Web service (monorepo `apps/api` + `apps/web`; this feature touches `apps/api` only)

**Performance Goals**: Bounded query counts — O(1) queries per upsert batch (was O(N)); overview aggregation without per-org snapshot queries; companies list with single grouped count

**Constraints**: Dedup contract (`build_review_hash`, `uq_review_org_hash`) frozen; additive-only schema changes; SQLite-compatible DDL; no Celery/queues; no new endpoints; API response shapes unchanged

**Scale/Scope**: Tens of organizations, thousands of reviews, small operator team

## Constitution Check

*GATE: evaluated against constitution v1.4.0 — PASS (pre- and post-design).*

| Principle | Check |
|---|---|
| I. MVP Scope Discipline | PASS — bugfix/perf/consistency only; no excluded feature introduced |
| II. Read-Only Collection | PASS — no provider write paths touched |
| III. Critical-Path Testing | PASS — new tests for upsert concurrency, aggregation, async session, zero-rating guard; dedup tests untouched and must stay green |
| IV. Scraper Reliability & Debuggability | STRENGTHENED — auth scraper gains challenge re-check + debug artifacts; parent runs stop lying; swallowed exceptions now logged |
| V. Simplicity (YAGNI) | PASS — BackgroundTasks reused (no Celery), stdlib logging (no deps), savepoints (no dialect forks) |
| VI. Deterministic Local Analytics | PASS — analyzer flow unchanged, still after hash |
| VII. Admin Panel Security | PASS — untouched; no creds in new logs (explicit rule in R6) |
| VIII. Multi-Provider Collection | PASS — 2GIS aligns to shared validity rule; single persistence path preserved |

No Complexity Tracking entries required.

## Project Structure

### Documentation (this feature)

```text
specs/010-backend-hardening/
├── plan.md              # This file
├── research.md          # Phase 0 — decisions R1–R9
├── data-model.md        # Phase 1 — entity/state changes
├── quickstart.md        # Phase 1 — validation guide
├── contracts/
│   └── api-deltas.md    # Phase 1 — semantic deltas of existing endpoints
├── checklists/
│   └── requirements.md
└── tasks.md             # Phase 2 (/speckit-tasks)
```

### Source Code (repository root)

```text
apps/api/
├── alembic/versions/
│   └── 0013_review_indexes_session_pending.py   # NEW: indexes + session_status enum value
├── app/
│   ├── main.py                    # CORS fail-closed; setup_logging() call
│   ├── core/
│   │   ├── config.py              # (comment only; no new settings)
│   │   └── logging.py             # NEW: setup_logging()
│   ├── models/
│   │   ├── enums.py               # SessionStatus.pending
│   │   └── review.py              # Index() entries in __table_args__
│   ├── api/
│   │   ├── scraper_sessions.py    # BackgroundTasks offload, pending state
│   │   └── companies.py           # batched branch_count
│   ├── services/
│   │   ├── review_service.py      # preload map + savepoint upsert, exact counters, logging
│   │   ├── scrape_service.py      # parent aggregation; snapshot warning; pending guard in get_session_status
│   │   ├── company_service.py     # branch_counts() grouped query
│   │   └── dashboard_service.py   # rating_delta takes org, batch snapshot load, reuse loaded reviews
│   └── scraper/
│       ├── markers.py             # NEW: shared BOT_MARKERS
│       ├── yandex_public.py       # import markers (re-export CAPTCHA_MARKERS)
│       ├── yandex_http.py         # import markers
│       ├── yandex_scrapeops.py    # import markers
│       ├── yandex_auth.py         # challenge re-check + debug artifacts
│       └── twogis_api.py          # markers base + rating>=1 guard
└── tests/
    ├── test_review_upsert_concurrency.py   # NEW
    ├── test_scrape_all_aggregation.py      # NEW
    ├── test_scraper_session_async.py       # NEW
    ├── test_markers.py                     # NEW (or folded into scraper tests)
    ├── test_twogis_api.py                  # extended: zero-rating exclusion
    └── test_cors_config.py                 # NEW: fail-closed startup
```

**Structure Decision**: existing `apps/api` layering preserved (api → services → models/scraper); only additive files (`core/logging.py`, `scraper/markers.py`, migration, tests).

## Design Notes (Phase 1 highlights)

- **Upsert (R1)**: one `SELECT ... WHERE organization_id = :org AND content_hash IN (:batch)` builds the map; loop consults map; inserts wrapped in `begin_nested()`; `IntegrityError` → savepoint rollback → targeted single-hash re-select → update path. Final single `commit()`. Counter semantics: `seen` = parsed batch size, `inserted` = successful nested flushes, `updated` = map hits + collision recoveries.
- **Aggregation (R2)**: pure logic in `execute_run`; statuses matrix per FR-004; zero-org bulk → `success` with zero counters.
- **Async session (R3)**: `pending` enum value; endpoints schedule background fns with own `SessionLocal`; duplicate request while pending returns pending without re-scheduling; `get_session_status` must not overwrite `pending` from file heuristics.
- **Auth scraper (R6 of audit / FR-006)**: after reviews navigation + `_open_reviews_tab`, re-check `_is_access_challenge(page.content())`; on challenge, `save_debug_artifacts(page)` and return `needs_manual_action` result with artifact paths — same shape as `yandex_public`.
- **Dashboard (FR-007)**: `rating_delta(org: Organization, ...)` signature takes the loaded org; new `_earliest_snapshots(org_ids, platforms, period_start)` grouped query (window function `ROW_NUMBER() OVER (PARTITION BY organization_id, platform ORDER BY captured_on)` — works on PG16 and SQLite 3.25+); `_platform_cards` filters the already-materialized `all_reviews` in Python when `platform == "all"`.
- **Companies (FR-008)**: `CompanyService.branch_counts() -> dict[UUID, int]` via `GROUP BY company_id`; `list_companies` uses it; single-company endpoints keep per-id count (1 query is fine there).

## Complexity Tracking

None — no constitution violations.
