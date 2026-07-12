# Research: Backend Hardening (010)

All unknowns from Technical Context resolved below. No NEEDS CLARIFICATION remain.

## R1. Upsert strategy for `ReviewService.upsert_reviews`

**Decision**: Preloaded `content_hash → Review` map (one query per batch) + per-review SAVEPOINT (`Session.begin_nested()`) around the insert `flush()`; single `commit()` at the end.

**Rationale**:
- A savepoint rollback on `IntegrityError` undoes only the colliding insert, never previously-flushed rows — fixes the batch-loss bug with minimal change to the existing ORM flow.
- Dialect-portable: savepoints work identically on Postgres 16 and SQLite test backend; no dual code paths.
- The update path is row-conditional (fill `response_text` only if newly present, set `response_first_seen_at` once, run analysis only when `analyzed_at IS NULL`) — expressing that in a single `ON CONFLICT DO UPDATE` statement is awkward and loses the analyzer flow; ORM keeps it readable.
- Preload eliminates the per-review SELECT (N+1 → 1 query). After a savepoint collision (concurrent writer), one targeted re-SELECT for that hash only.
- Counters become exact: `inserted` incremented only after a successful nested flush; collision path increments `updated`.

**Alternatives considered**:
- *Postgres `INSERT ... ON CONFLICT DO UPDATE`* — fastest, but requires dialect-specific statement + separate SQLite branch (or `sqlite_on_conflict`), duplicates the conditional update logic in SQL, and bypasses the Python analyzer for the update path. Rejected: complexity > benefit at tens-of-orgs scale.
- *Per-review `commit()`* — survives collisions but breaks run atomicity into hundreds of tiny transactions and is slow. Rejected.

## R2. Parent run aggregation (`ScrapeService.execute_run` bulk branch)

**Decision**: Collect each child's terminal `(status, seen, inserted, updated)` in the loop; after the loop set parent:
- `failed` if children exist and all are `failed`;
- `needs_manual_action` if no child succeeded and ≥1 is `needs_manual_action`;
- `success` otherwise (≥1 success, or zero organizations);
- counters = sums over children.

Child exceptions already terminalize as `failed` inside `_scrape_organization` — aggregation reads the child row after the call, so a crashed child cannot hang the parent.

**Alternatives considered**: new `partial` enum value — rejected (enum migration + frontend changes; spec assumption says no new enum value; child rows keep the detail).

## R3. Async session login/check

**Decision**:
- Add `pending` to `SessionStatus` enum + `ALTER TYPE session_status_enum ADD VALUE 'pending'` migration (Postgres); SQLite stores strings — no-op (same pattern as migration 0003/0005/0006).
- Endpoints `POST /api/scraper/yandex/login` and `POST /session/check` take `BackgroundTasks`: set session row to `pending`, commit, schedule `_run_login_background` / `_run_check_background` (own `SessionLocal`, same pattern as `_run_scrape_background` in `api/scrape_runs.py`), return current (pending) state immediately — 202 becomes truthful.
- If a login/check is already `pending`, a second request returns the pending state without scheduling a duplicate task (deterministic reject; edge case from spec).
- **Guard**: `get_session_status()` currently overwrites status from file existence (`scrape_service.py:228-236`) — it must NOT override `pending`, otherwise polling would show `valid` mid-login.

**Alternatives considered**: keep sync + return 200 — rejected: blocks a worker for tens of seconds, inconsistent with scrape endpoints and with US3 acceptance (respond < 1s).

## R4. Shared bot-detection markers

**Decision**: New `app/scraper/markers.py` exporting `BOT_MARKERS: tuple[str, ...]` (the identical 4-tuple currently copy-pasted). `yandex_public` re-exports it as `CAPTCHA_MARKERS = BOT_MARKERS` for backward compatibility (imported by `yandex_auth.py` and referenced in CLAUDE.md/tests); `yandex_http` and `yandex_scrapeops` import and alias. `twogis_api.BOT_MARKERS` becomes `markers.BOT_MARKERS + (its 2GIS-specific extras)`. Preserve the "no bare 'captcha'" comment (false-positive on `captchapgrd`) in the shared module.

## R5. Review indexes migration

**Decision**: Migration `0013_review_indexes.py`, additive only:
- `ix_reviews_org_review_date` on `(organization_id, review_date)`
- `ix_reviews_org_first_seen` on `(organization_id, first_seen_at)`
- `ix_reviews_org_platform` on `(organization_id, platform)`

Plain composite B-trees (no `DESC` modifiers — Postgres scans B-trees backward for `ORDER BY ... DESC`, and `.nullslast()` ordering still benefits from the filter prefix; keeps DDL portable to SQLite). Mirror as `Index(...)` entries in `Review.__table_args__` so SQLite `create_all` test schema matches. No table rewrite; safe at current volume.

**Alternatives considered**: `postgresql_ops`/DESC index — rejected as premature; can add later if EXPLAIN shows need.

## R6. Logging setup

**Decision**: `app/core/logging.py` with `setup_logging()` using stdlib `logging.basicConfig(level=INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")`, called once at import in `app/main.py` (and in `scripts/` entrypoints if needed). Module loggers via `logging.getLogger(__name__)`. Mandatory log points:
- `scrape_service._scrape_organization` exception path — `logger.exception` with org id + run id;
- snapshot `except` (`_persist_scrape_result`) — `logger.warning` with org id (no longer silent);
- `review_service` savepoint-collision path — `logger.warning` with org id + hash prefix;
- `main.py` CORS failure — raised error is self-explanatory.
Never log credentials, storage-state contents, or full proxy URLs (reuse `proxy_pool.redact` where relevant). No external deps, no uvicorn config changes.

## R7. CORS fail-closed

**Decision**: In `main.py`, after parsing `settings.api_cors_origins`: `if not origins: raise RuntimeError("API_CORS_ORIGINS must list at least one origin (credentials mode); refusing to fall back to '*'")`. Config default stays `"http://localhost:3000"` so local/dev keeps working; only an explicitly emptied env var fails startup. `.env.example` gets a comment.

## R8. 2GIS zero-rating guard

**Decision**: `_map_review` returns `ParsedReview | None`; returns `None` when parsed rating < 1. Caller (`_fetch_reviews` loop) skips `None` (they still count toward nothing — they are never appended, `reviews_seen` counts only persisted-candidate reviews, matching Yandex parser behavior which never emits sub-1 ratings). Matches `parser.py` guard (`rating < 1` → skip). No backfill deletion of existing rating-0 rows (out of scope per spec assumption).

## R9. Test strategy

- `test_review_upsert_concurrency.py`: simulate mid-batch `IntegrityError` (insert duplicate row via second session between preload and flush) → assert earlier inserts survive, counters exact, colliding row resolved as update.
- `test_scrape_all_aggregation.py`: stub scrapers per-org outcomes → assert parent status matrix (all-failed / mixed / all-captcha / zero-orgs) + counter roll-up.
- `test_scraper_session_async.py`: login/check endpoints return immediately with `pending`; background fn updates to terminal; second login while pending does not double-schedule; `get_session_status` does not clobber `pending`.
- `test_twogis_api.py`: extend — zero/missing rating review excluded.
- `test_markers.py` or extend existing scraper tests: all scrapers share the base tuple.
- CORS: unit test that empty origins raises at app construction (import-time guard refactored to a function for testability).
- Existing suites (`test_review_deduplication.py`, contract tests) must pass unchanged.
