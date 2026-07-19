# Implementation Plan: Twice-Daily Review Sync with Removal Tracking

**Branch**: `011-review-removal-sync` | **Date**: 2026-07-19 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/011-review-removal-sync/spec.md`

## Summary

Make the automated reviews job react to platform counter mismatches in **both** directions and teach the pipeline to track reviews that disappear from a platform. Core mechanics: (1) `ScrapeResult`/`ScrapeRun` gain a `full_pass` coverage indicator set only when pagination was demonstrably exhausted (no cap hit, no skipped page); (2) after a successful full pass, reviews of that organization+platform whose `content_hash` was not seen in the pass are marked `removed_at = now` (kept, never deleted); a review seen again clears `removed_at` on the existing row — the dedup contract (`build_review_hash`, `uq_review_org_hash`) is untouched; (3) `JobRunner._run_reviews` compares the platform counter against **non-removed** collected reviews and scrapes on `!=` instead of only `>`, requesting uncapped pagination (`limit=math.inf`, CLI's `ALL_REVIEWS_MAX_PAGES` guard); (4) a zero-result full pass with previously collected reviews is an anomaly and never mass-marks removals unless the platform counter corroborates 0; (5) optional `force_full_every_days` job option forces a periodic full pass; (6) twice-daily production schedule is a documented cron configuration (`0 4,16 * * *` metrics, `0 5,17 * * *` reviews), applied via the existing `PATCH /api/jobs/{id}` — no scheduling code changes.

## Technical Context

**Language/Version**: Python 3.11 (FastAPI backend), TypeScript / Next.js 14 App Router (web)

**Primary Dependencies**: FastAPI, SQLAlchemy 2.x, Alembic, APScheduler (existing in-process cron), requests + BeautifulSoup (`yandex_http`), 2GIS public API client (`twogis_api`); no new dependencies

**Storage**: PostgreSQL 16 (prod), SQLite for pytest; additive columns only — `reviews.removed_at` (nullable timestamptz), `scrape_runs.full_pass` (bool, default false), migration `0016`

**Testing**: pytest (`apps/api/tests`), Playwright E2E for web (`apps/web`, existing suite untouched unless UI touched)

**Target Platform**: Docker Compose on the existing production host; scheduler already runs in the FastAPI lifespan

**Project Type**: Monorepo web app (`apps/api` + `apps/web`)

**Performance Goals**: n/a beyond existing — tens of organizations, sequential job walk with per-org delay; removal marking is one extra UPDATE per successful full pass

**Constraints**: Read-only toward platforms; deterministic decisions with human-readable reasons per org; `needs_manual_action` semantics unchanged; no Celery/queues; dedup contract frozen

**Scale/Scope**: ~tens of orgs × 2 platforms; ≤ ~1–2k reviews per org; hash `NOT IN` set per full pass is small

## Constitution Check

*GATE: v1.4.0 — evaluated pre-Phase-0 and re-checked post-design. PASS, no violations.*

| Principle | Status | Notes |
|---|---|---|
| I. MVP Scope Discipline | PASS | Extends existing jobs/scrape pipeline; no excluded feature (no replies, no new provider, no LLM, no notifications infra). |
| II. Read-Only Collection | PASS | Removal state is a *local observation* ("no longer seen on platform"); nothing is written to platforms. Removed reviews are retained and display-only. |
| III. Critical-Path Testing | PASS | New decision logic, removal marking, reappearance un-marking, and dedup-unaffected tests are mandatory (see quickstart + tasks). |
| IV. Scraper Reliability & Debuggability | PASS | `full_pass` adds coverage observability to every `ScrapeRun`; failure/`needs_manual_action` semantics and debug artifacts unchanged; zero-result anomaly surfaces with an explicit error code instead of silent data change. |
| V. Simplicity (YAGNI) | PASS | No new services/queues; one dataclass field, two columns, one job-option key; reuses CLI's uncapped-pagination pattern. |
| VI. Deterministic Local Analytics | PASS | Analytics untouched; `removed_at` never feeds analysis or the dedup hash. |
| VII. Admin Panel Security | PASS | No auth changes; job mutations stay behind existing admin-only endpoints. |
| VIII. Multi-Provider Collection | PASS | `full_pass` is set inside each provider scraper but flows through the shared `ScrapeResult` contract; persistence/dedup path stays single. |

## Project Structure

### Documentation (this feature)

```text
specs/011-review-removal-sync/
├── spec.md
├── plan.md              # This file
├── research.md          # Phase 0
├── data-model.md        # Phase 1
├── quickstart.md        # Phase 1
├── contracts/
│   └── api-deltas.md    # Phase 1 — endpoint/response deltas
├── checklists/
│   └── requirements.md
└── tasks.md             # /speckit-tasks output (not created by plan)
```

### Source Code (repository root)

```text
apps/api/
├── app/
│   ├── scraper/
│   │   ├── types.py            # ScrapeResult.full_pass field
│   │   ├── yandex_http.py      # set full_pass on exhausted pagination
│   │   └── twogis_api.py       # set full_pass on empty-page termination
│   ├── models/
│   │   ├── review.py           # removed_at column
│   │   └── scrape_run.py       # full_pass column
│   ├── services/
│   │   ├── review_service.py   # upsert returns seen hashes / clears removed_at; mark_removed_missing(); listing filters
│   │   ├── scrape_service.py   # persist full_pass; invoke removal marking after successful full pass
│   │   └── job_runner.py       # != trigger on non-removed count; math.inf overrides; force_full_every_days
│   ├── schemas/
│   │   ├── review.py           # removed_at in response
│   │   └── scrape.py           # full_pass in run response
│   └── api/
│       └── reviews.py          # `removed` filter param (active|removed|all)
├── scripts/
│   └── scrape_reviews.py       # ALL_REVIEWS_MAX_PAGES moves to a shared location (reused by job runner)
├── alembic/versions/
│   └── 0016_review_removal_tracking.py
└── tests/
    ├── test_review_removal.py          # marking, un-marking, scoping, zero-guard
    ├── test_job_runner.py              # decision matrix extension (existing file)
    └── test_scraper_full_pass.py       # per-scraper full_pass semantics

apps/web/
├── lib/types.ts                # removed_at on Review, full_pass on ScrapeRun
├── lib/api.ts                  # removed filter passthrough
└── app/... + components/...    # removed badge + "show removed" toggle on org reviews table
```

**Structure Decision**: Existing monorepo layout; all changes are additive edits inside the current layering (api → services → models/scraper). No new modules except the migration and test files.

## Complexity Tracking

No constitution violations — table not required.
