# Tasks: Backend Hardening — Scrape Reliability, Performance, Data Consistency

**Input**: Design documents from `specs/010-backend-hardening/`
**Prerequisites**: plan.md, spec.md, research.md (R1–R9), data-model.md, contracts/api-deltas.md

**Tests**: REQUIRED — SC-005 and constitution Principle III demand automated coverage for every fixed defect. All paths relative to repo root.

## Phase 1: Setup

- [X] T001 Create shared marker module `apps/api/app/scraper/markers.py`: export `BOT_MARKERS: tuple[str, ...]` with the 4 shared markers ("Обнаружена защита от ботов", "showcaptcha", "SmartCaptcha", "Подтвердите, что запросы") and carry over the "no bare 'captcha' (captchapgrd false-positive)" comment from `yandex_public.py`
- [X] T002 Create logging setup `apps/api/app/core/logging.py`: `setup_logging()` via stdlib `logging.basicConfig(level=INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")`, idempotent (guard against double-config); call it in `apps/api/app/main.py` before app construction

## Phase 2: Foundational (blocking prerequisites)

- [X] T003 Add `pending = "pending"` to `SessionStatus` in `apps/api/app/models/enums.py`
- [X] T004 Add index definitions to `Review.__table_args__` in `apps/api/app/models/review.py`: `Index("ix_reviews_org_review_date", "organization_id", "review_date")`, `Index("ix_reviews_org_first_seen", "organization_id", "first_seen_at")`, `Index("ix_reviews_org_platform", "organization_id", "platform")` (keep existing UniqueConstraint first)
- [X] T005 Create migration `apps/api/alembic/versions/0013_review_indexes_session_pending.py`: upgrade = `ALTER TYPE session_status_enum ADD VALUE IF NOT EXISTS 'pending'` (Postgres-only guard, no-op on SQLite; follow migration 0003 pattern) + `op.create_index` for the three indexes from T004; downgrade = drop the three indexes only, docstring notes enum value is irreversible
- [X] T006 Verify migration on both backends: `alembic upgrade head`, `alembic downgrade -1`, `alembic upgrade head` against Postgres; `pytest -x -q` (SQLite create_all) still green

**Checkpoint**: schema + enum + shared modules in place; all user stories unblocked.

## Phase 3: User Story 1 — Reviews never lost during overlapping scrapes (P1) 🎯 MVP

**Goal**: Batch-safe upsert with exact counters (FR-001, FR-002, FR-003 insert-path). **Independent test**: `pytest tests/test_review_upsert_concurrency.py tests/test_review_deduplication.py -v`.

- [X] T007 [US1] Rewrite `upsert_reviews` in `apps/api/app/services/review_service.py`: (1) build hashes for the whole batch first; (2) preload existing rows in one query `WHERE organization_id = :org AND content_hash IN (:hashes)` into a `dict[hash, Review]`; (3) map hit → existing update path (unchanged semantics: `last_seen_at`, conditional `response_text`/`response_first_seen_at`, analysis if `analyzed_at is None`), `updated += 1`; (4) miss → insert inside `with self.db.begin_nested():` + `flush()`, `inserted += 1` on success; (5) on `IntegrityError` the savepoint auto-rolls back — re-select that single hash, apply update path, `updated += 1`, `logger.warning` with org id + hash prefix (first 12 chars, never review text); (6) single `self.db.commit()` at the end; add module logger. Do NOT touch `build_review_hash` inputs or call order (hash before analysis)
- [X] T008 [P] [US1] New test `apps/api/tests/test_review_upsert_concurrency.py`: (a) mid-batch collision — insert a conflicting row via a second `SessionLocal` between preload and flush (monkeypatch or event hook), assert earlier batch inserts survive commit, colliding review resolved as update, counters exact (seen/inserted/updated); (b) counters-vs-DB assertion: after upsert, `inserted == new row count delta`, `updated == touched rows`; (c) re-scrape idempotency: second identical batch → 0 inserted, all updated
- [X] T009 [US1] Run and pass: `pytest tests/test_review_upsert_concurrency.py tests/test_review_deduplication.py tests/test_scrape_persistence.py -v` (adjust last filename to the existing persistence suite) — dedup contract untouched

**Checkpoint**: US1 deliverable — data-loss bug closed, counters trustworthy.

## Phase 4: User Story 2 — Bulk scrape reports true outcome (P1)

**Goal**: Parent run aggregation (FR-004). **Independent test**: `pytest tests/test_scrape_all_aggregation.py -v`.

- [X] T010 [US2] Update bulk branch of `execute_run` in `apps/api/app/services/scrape_service.py`: collect each child's terminal `(status, reviews_seen, reviews_inserted, reviews_updated)` after `_scrape_organization` returns (re-read child row); after loop set parent status per matrix — children non-empty & all `failed` → `failed`; no `success` & ≥1 `needs_manual_action` → `needs_manual_action`; else `success` (incl. zero orgs); parent counters = sums; keep `finished_at`/commit
- [X] T011 [P] [US2] New test `apps/api/tests/test_scrape_all_aggregation.py`: stub scrapers (monkeypatch `ScrapeService` scraper attrs) to produce per-org outcomes; assert parent status for: all-failed, all-captcha (`needs_manual_action`), mixed failed+captcha (→ `needs_manual_action`), mixed with ≥1 success (→ `success`), zero organizations (→ `success`, zero counters); assert parent counters equal child sums; assert a child raising an exception terminalizes as `failed` and does not hang aggregation

**Checkpoint**: US2 deliverable — no more falsely green bulk runs.

## Phase 5: User Story 3 — Non-blocking session login/check (P2)

**Goal**: Truthful 202 + `pending` polling (FR-005). **Independent test**: `pytest tests/test_scraper_session_async.py -v`.

- [X] T012 [US3] Add background execution to `apps/api/app/api/scraper_sessions.py`: module-level `_run_login_background()` / `_run_check_background()` opening own `SessionLocal` (mirror `_run_scrape_background` in `api/scrape_runs.py`) calling `ScrapeService.login_operator()` / `check_session()`; `yandex_login` and `check_session` endpoints take `BackgroundTasks`, set session status to `SessionStatus.pending` + commit, schedule task, return current (pending) state immediately; if already `pending` → return pending state WITHOUT scheduling (message "Login already in progress"); `POST /session/check` becomes `status_code=202`
- [X] T013 [US3] Guard `get_session_status` in `apps/api/app/services/scrape_service.py`: file-existence heuristics must not overwrite `SessionStatus.pending`; also ensure `login_operator`/`check_session` always transition `pending → terminal` even on exception (wrap in try/finally or except → `needs_manual_action`/`expired` + log)
- [X] T014 [P] [US3] New test `apps/api/tests/test_scraper_session_async.py` (TestClient + monkeypatched `YandexAuthScraper.login/check_session` with a slow/flagging stub): (a) login returns 202 immediately with `status == "pending"` before stub completes; (b) after background task runs, `GET /session` shows terminal status; (c) second login while pending returns pending and does not schedule a second task (count stub invocations); (d) `get_session_status` does not clobber `pending` despite existing storage-state file

**Checkpoint**: US3 deliverable — API never blocks on Playwright.

## Phase 6: User Story 4 — Auth scraper detects late challenges (P2)

**Goal**: Challenge re-check + debug artifacts in operator-auth mode (FR-006). **Independent test**: auth-scraper unit test with stubbed page HTML.

- [X] T015 [US4] Update `scrape` in `apps/api/app/scraper/yandex_auth.py`: after the `/reviews` navigation (and after `_open_reviews_tab`), re-check `public._is_access_challenge(page.content())`; on any challenge detection (both the existing early check and the new ones) call `save_debug_artifacts` (import from `app.scraper.debug_artifacts`, same call shape as `yandex_public`) and populate `result.debug_screenshot`/`result.debug_html` before returning `needs_manual_action`
- [X] T016 [P] [US4] Extend/create auth scraper test in `apps/api/tests/test_yandex_auth_scraper.py`: stub Playwright page/context (monkeypatch `sync_playwright` or extract a testable `_scrape_with_page(page)` helper) — challenge HTML appearing only after reviews navigation → result `needs_manual_action`, `error_code="access_challenge"`, debug artifact paths set; normal HTML → parsed reviews unchanged

**Checkpoint**: US4 deliverable — captcha never parsed as reviews in auth mode.

## Phase 7: User Story 5 — Dashboard and lists stay fast (P2)

**Goal**: Kill N+1s, add index-backed queries (FR-007, FR-008; FR-009 landed in Phase 2). **Independent test**: existing dashboard/companies suites green + query-count assertions.

- [X] T017 [US5] Refactor `apps/api/app/services/dashboard_service.py`: (1) change `rating_delta(self, org: Organization, platform, period_start)` to take the loaded org (drop `db.get`); update all callers (`_network_rating_delta`, `_worst_locations`, `_rating_drops`, `_platform_cards` chain); (2) add `_earliest_snapshots(org_ids, period_start) -> dict[(org_id, platform), float]` using one window query `ROW_NUMBER() OVER (PARTITION BY organization_id, platform ORDER BY captured_on ASC)` filtered `captured_on >= period_start AND rating IS NOT NULL` — use it from `overview` and pass the map down instead of per-org snapshot queries; (3) `_platform_cards`: when computing per-platform review sets, filter the already-materialized `all_reviews` in Python instead of issuing a second full `Review` query
- [X] T018 [US5] Batch branch counts: add `branch_counts(self) -> dict[UUID, int]` (single `GROUP BY company_id` over organizations) to `apps/api/app/services/company_service.py`; use it in `list_companies` in `apps/api/app/api/companies.py` (single-company endpoints keep `branch_count(id)`)
- [X] T019 [P] [US5] Add query-count regression test `apps/api/tests/test_query_counts.py`: SQLAlchemy `event.listens_for(engine, "before_cursor_execute")` counter fixture; assert (a) `upsert_reviews` with 50 new reviews issues O(1) SELECTs (≤3 statements besides INSERTs), (b) `DashboardService.overview` for 5 orgs × 2 platforms issues a bounded statement count (record actual, assert it does not scale with org count by comparing 2-org vs 5-org runs), (c) `GET /api/companies` with 10 companies issues ≤3 SELECTs; assert API payloads unchanged vs pre-refactor shape (golden expectations within test)

**Checkpoint**: US5 deliverable — bounded query counts, identical payloads.

## Phase 8: User Story 6 — Consistent data rules and visible errors (P3)

**Goal**: FR-010–FR-013. **Independent test**: `pytest tests/test_twogis_api.py tests/test_markers.py tests/test_cors_config.py -v`.

- [X] T020 [P] [US6] 2GIS rating guard in `apps/api/app/scraper/twogis_api.py`: `_map_review` returns `ParsedReview | None` (None when rating < 1 after parse); `_fetch_reviews` skips None entries; extend `apps/api/tests/test_twogis_api.py` — review with `rating: null` / `"abc"` / `0` excluded, valid ones kept
- [X] T021 [P] [US6] Adopt shared markers from T001: `apps/api/app/scraper/yandex_public.py` → `from app.scraper.markers import BOT_MARKERS as CAPTCHA_MARKERS` (keep name exported for `yandex_auth.py` back-compat); `yandex_http.py` and `yandex_scrapeops.py` → import `BOT_MARKERS`; `twogis_api.py` → `BOT_MARKERS = markers.BOT_MARKERS + (2GIS-specific extras)`; new `apps/api/tests/test_markers.py` asserting all four modules share the base tuple (subset/identity checks)
- [X] T022 [P] [US6] Logging on swallowed exceptions in `apps/api/app/services/scrape_service.py`: snapshot `except` → `logger.warning("snapshot capture failed org=%s run=%s", ..., exc_info=True)` before rollback; `_scrape_organization` except → `logger.exception` with org+run ids; audit for other bare excepts in `apps/api/app/` and add warnings (never log credentials/storage-state/proxy passwords — reuse `proxy_pool.redact` where applicable)
- [X] T023 [P] [US6] CORS fail-closed: extract origin parsing in `apps/api/app/main.py` to `_cors_origins(settings) -> list[str]` raising `RuntimeError("API_CORS_ORIGINS must list at least one origin; refusing to fall back to '*'")` when empty; new `apps/api/tests/test_cors_config.py` asserting the raise and the parsed list for a normal value; add comment to `.env.example` documenting fail-closed behavior

**Checkpoint**: US6 deliverable — uniform data rules, observable failures, safe CORS.

## Phase 9: Polish & Cross-Cutting

- [X] T024 Remove unused `import time` from `apps/api/app/scraper/yandex_public.py` (audit finding #12)
- [X] T025 Full verification gate per quickstart.md: `pytest -v` in `apps/api` (all suites incl. new), then `npm run lint && npm run test:e2e` in `apps/web` (no frontend changes expected — gate confirms no regression)
- [X] T026 Update `CLAUDE.md` architecture notes: shared `scraper/markers.py`, `SessionStatus.pending` + async login/check semantics, parent-run aggregation rule, upsert savepoint strategy (short additions to existing sections)

## Dependencies

- Phase 1 (T001–T002) and Phase 2 (T003–T006): sequential foundation; T005 depends on T003+T004
- US1 (T007–T009): after Phase 2; independent of US2–US6
- US2 (T010–T011): after Phase 2; touches `scrape_service.py` — coordinate with T013/T022 (same file, run sequentially with US3/US6 file edits)
- US3 (T012–T014): after T003 (pending enum)
- US4 (T015–T016): after T001 only
- US5 (T017–T019): after Phase 2 (indexes); T019 after T007 (query-count test asserts new upsert)
- US6 (T020–T023): T021 after T001; rest independent
- Polish (T024–T026): last

**Story order**: US1 → US2 → US3 → US4 → US5 → US6 (priority order); US4/US6 can interleave earlier if parallelized.

## Parallel Execution Examples

- After Phase 2: T007 (US1) ∥ T015 (US4) ∥ T020 (US6) — different files
- Test authoring: T008 ∥ T011 ∥ T014 ∥ T016 ∥ T019 — all new test files
- US6 tasks T020 ∥ T021 ∥ T023 (T022 shares `scrape_service.py` with T010/T013 — sequence those three)

## Implementation Strategy

MVP = Phase 1 + Phase 2 + US1 (T001–T009): closes the data-loss bug with exact counters — deliverable alone. Then US2 (truthful bulk runs) completes the P1 pair. Each subsequent story is an independently testable increment; run `pytest tests/test_review_deduplication.py` after every story touching persistence.
