# Tasks: Twice-Daily Review Sync with Removal Tracking

**Input**: Design documents from `/specs/011-review-removal-sync/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/api-deltas.md, quickstart.md

**Tests**: INCLUDED — constitution Principle III makes dedup/scrape-persistence/job-decision tests mandatory before merge; spec lists the required scenarios explicitly.

**Organization**: Grouped by user story; US1 is the MVP increment, US2 makes it fire automatically.

## Format: `[ID] [P?] [Story] Description`

## Phase 1: Setup

- [x] T001 Create feature branch `feat/review-removal-sync` off `main`

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Schema + shared contracts every story builds on. No story work before this phase is done.

- [x] T002 Alembic migration `apps/api/alembic/versions/0016_review_removal_tracking.py`: add `reviews.removed_at` (timestamptz NULL) and `scrape_runs.full_pass` (boolean NOT NULL DEFAULT false); downgrade drops both (see data-model.md)
- [x] T003 [P] Add `removed_at: Mapped[datetime | None]` to `apps/api/app/models/review.py` (nullable, no default; comment: never feeds content_hash)
- [x] T004 [P] Add `full_pass: Mapped[bool]` (default False, server_default "false") to `apps/api/app/models/scrape_run.py`
- [x] T005 [P] Add `full_pass: bool = False` field to `ScrapeResult` in `apps/api/app/scraper/types.py`
- [x] T006 [P] Expose new fields in schemas: `removed_at` in `apps/api/app/schemas/review.py`, `full_pass` in `apps/api/app/schemas/scrape.py`; mirror both in `apps/web/lib/types.ts`

**Checkpoint**: `alembic upgrade head` clean; existing pytest suite still green.

## Phase 3: User Story 1 — Detect and record removed reviews (Priority: P1) 🎯 MVP

**Goal**: A successful full scrape pass marks locally-stored reviews that disappeared from the platform as removed (kept + labeled), un-marks reappearing ones, and never false-flags on partial/failed/zero-anomaly passes.

**Independent test**: Simulate scrape results against seeded reviews (no network): full pass missing a review → marked; partial pass → nothing marked; reappearance → un-marked, no duplicate; zero-result guard honored. Then via API: default list hides removed, `?removed=removed` shows them.

- [x] T007 [P] [US1] Write failing tests for `full_pass` semantics in `apps/api/tests/test_scraper_full_pass.py`: yandex_http sets True only on exhausted pagination (fresh==0 on page>1); False when limit cap hit, max_pages cap hit, a page was skipped by transient fetch error, metrics_only, bot-wall, or error; twogis sets True only on natural empty-page end, False on limit/max_pages cap (mock `_fetch`/HTTP layer per existing scraper-test patterns)
- [x] T008 [US1] Implement `full_pass` in `apps/api/app/scraper/yandex_http.py`: track skipped pages + loop-exit cause per research.md R1; set `result.full_pass` before return
- [x] T009 [US1] Implement `full_pass` in `apps/api/app/scraper/twogis_api.py`: `_fetch_reviews` reports coverage (returns reviews + exhausted flag or sets it via small result object); `scrape()` sets `result.full_pass`; T007 tests green
- [x] T010 [P] [US1] Write failing tests for removal marking in `apps/api/tests/test_review_removal.py`: (a) full pass missing one review → `removed_at` set, others untouched; (b) partial pass (`full_pass=False`) → nothing marked; (c) removed review seen again → same row un-marked, no insert, dedup counters exact; (d) marking scoped to org+platform (yandex pass never touches gis2 rows); (e) zero-result full pass with non-removed rows and platform counter ≠ 0 → run `failed`, `error_code="empty_full_pass"`, nothing marked; (f) same but platform counter == 0 → all marked; (g) `build_review_hash` inputs untouched (import contract check)
- [x] T011 [US1] `apps/api/app/services/review_service.py`: `upsert_reviews` returns the set of seen content hashes (extend return or add companion accessor); `_apply_update` sets `existing.removed_at = None`; new `mark_removed_missing(organization_id, platform, seen_hashes, now) -> int` doing the scoped `UPDATE ... WHERE removed_at IS NULL AND content_hash NOT IN (...)`
- [x] T012 [US1] `apps/api/app/services/scrape_service.py` `_persist_scrape_result`: persist `run.full_pass = result.full_pass`; on success path with `full_pass`, apply zero-guard (org platform counter per research.md R4; on violation finalize `failed`/`empty_full_pass` without data changes) else call `mark_removed_missing`; T010 tests green
- [x] T013 [US1] API listing filter: `removed: active|removed|all` (default `active`) query param in `apps/api/app/api/reviews.py` for per-org and global feed endpoints; filter logic in `ReviewService.list_for_organization`/`list_global` (`removed_at IS NULL` / `IS NOT NULL` / no filter); invalid value → 422; extend existing API contract tests in `apps/api/tests/` for default-hides-removed and explicit views
- [x] T014 [US1] Web: pass `removed` filter through `apps/web/lib/api.ts`; org reviews table (`apps/web/components/`) gets a "показать удалённые" toggle and a labeled badge with `removed_at` date for removed rows

**Checkpoint**: US1 fully testable via pytest + manual API; nothing yet triggers automatically.

## Phase 4: User Story 2 — Trigger on any counter mismatch (Priority: P2)

**Goal**: The reviews job scrapes on `platform_total != non-removed collected` (both directions) and requests uncapped pagination so full passes are actually full.

**Independent test**: `apps/api/tests/test_job_runner.py` decision matrix — higher → scrape, lower → scrape, equal → skip (removed rows excluded from count), None → metrics-first skip; scrape call carries `limit=math.inf`.

- [x] T015 [P] [US2] Extend `apps/api/tests/test_job_runner.py` with failing tests: platform 8 vs 10 non-removed → scrape (old behavior skipped); 12 vs 10 → scrape; 10 vs 10 non-removed + 2 removed → skip "counters match"; counter None → unchanged skip; `execute_run` invoked with `limit=math.inf` and shared max-pages guard
- [x] T016 [US2] Move `ALL_REVIEWS_MAX_PAGES` from `apps/api/scripts/scrape_reviews.py` to a shared location (`apps/api/app/core/config.py` or `app/scraper/__init__` constant) and import it back in the script (behavior identical)
- [x] T017 [US2] `apps/api/app/services/job_runner.py` `_run_reviews`: count only `removed_at IS NULL`; replace `>`-only trigger with `!=` (drop the "площадка показывает меньше" skip branch, keep None-skip); update reason strings; call `execute_run(scrape_run.id, limit=math.inf, max_pages=ALL_REVIEWS_MAX_PAGES)`; T015 green

**Checkpoint**: End-to-end automatic reconciliation works from a job run.

## Phase 5: User Story 3 — Twice-daily production schedule (Priority: P3)

**Goal**: Documented + applied twice-daily configuration; zero code.

**Independent test**: After PATCHing crons, `/jobs` shows two runs per job per day; reviews runs see same-cycle metrics counters.

- [x] T018 [P] [US3] Document the recommended schedule (`0 4,16 * * *` metrics, `0 5,17 * * *` reviews, Europe/Moscow, reviews trail metrics by 1h) in `README.md` ops/jobs section, referencing `PATCH /api/jobs/{id}` and the `/jobs` page
- [ ] T019 [US3] Apply on production after deploy: PATCH the four jobs' `schedule_cron` + `is_enabled=true` per quickstart.md; verify next cycle in `/jobs` run history (operator step — record outcome in PR/notes)

## Phase 6: User Story 4 — Periodic forced full pass (Priority: P4)

**Goal**: Optional `force_full_every_days` job option bounds silent drift when adds and removals cancel out.

**Independent test**: Counters match + last full pass older than N days → scrape with forced-refresh reason; recent full pass → skip; option absent → identical to US2 rules.

- [x] T020 [P] [US4] Extend `apps/api/tests/test_job_runner.py`: forced-refresh triggers on stale/absent last full pass, skips on fresh one, disabled by default; reason string names forced refresh; add options-validation test (`force_full_every_days` must be int ≥ 1 → else 422) to `apps/api/tests/test_jobs_api.py`
- [x] T021 [US4] Implement: last-full-pass lookup (`scrape_runs` where `status=success AND full_pass AND mode=platform job mode`) + forced-scrape branch in `apps/api/app/services/job_runner.py`; validate the options key in the jobs update path (`apps/api/app/api/jobs.py` / `app/services/job_service.py`); T020 green

## Phase 7: Polish & Cross-Cutting

- [x] T022 [P] Update `CLAUDE.md` (jobs section: `!=` trigger over non-removed reviews, `full_pass`, removal marking, `empty_full_pass`, `force_full_every_days`; dedup section: reappearance un-marks) and `specs/011-review-removal-sync/` docs if implementation deviated
- [x] T023 Verification gate: `cd apps/api && pytest -v` (incl. `test_review_deduplication.py` untouched-contract check), then `cd apps/web && npm run lint && npm run test:e2e`; run quickstart.md manual E2E steps 1–5 on the local stack

## Dependencies

```text
Phase 2 (T002–T006) ──▶ US1 (T007–T014) ──▶ US2 (T015–T017) ──▶ US3 (T018–T019, docs-only, could run anytime)
                                        └──▶ US4 (T020–T021, needs full_pass rows from US1 + runner from US2)
Polish (T022–T023) last.
```

- US1 blocks US2 (non-removed count + full_pass must exist for the `!=` rule to converge).
- US3 is code-independent (docs/config) — can be written in parallel, applied only after US1+US2 deploy.
- US4 depends on US1 (`scrape_runs.full_pass`) and touches the same runner as US2 → sequence after US2.

## Parallel Opportunities

- Phase 2: T003, T004, T005, T006 in parallel after T002.
- US1: T007 ∥ T010 (different test files) before their implementations; T013 ∥ T014 (api vs web).
- T015, T018, T020, T022 are [P] against neighbors in their phases.

## Implementation Strategy

MVP = Phase 2 + US1: removal state exists, verifiable via manual scrape + API. US2 turns it on automatically; US3 is a config rollout; US4 is optional hardening. Ship US1+US2 together in one PR (US1 alone changes default list behavior but nothing marks removals in prod until jobs request full passes); US3 is a post-deploy operator action; US4 can ride the same PR or follow up.
