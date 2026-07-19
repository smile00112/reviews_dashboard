# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Internal, read-only dashboard for collecting and displaying Yandex Maps organization reviews. Monorepo: `apps/api` (FastAPI + Playwright scraper) and `apps/web` (Next.js). Postgres 16 store. There is no application-level auth — it's an internal tool for a small operator team tracking ~tens of organizations.

## Commands

Full stack (Postgres + API + web):
```bash
cp .env.example .env
docker compose up --build   # web :3000, api :8000, health :8000/health
```

API (`apps/api`):
```bash
pip install -e ".[dev]"
playwright install chromium   # required: scraper drives headless Chromium
alembic upgrade head          # apply migrations
uvicorn app.main:app --reload
pytest -v                     # all tests
pytest tests/test_review_deduplication.py -v          # single file
pytest tests/test_review_deduplication.py::test_name  # single test
```

Web (`apps/web`):
```bash
npm install
npm run dev
npm run lint
npm run test:e2e   # Playwright E2E (expects API + web running)
```

Verification gate (from README): `pytest -v` in api, then `npm run lint && npm run test:e2e` in web.

## Architecture

### Backend layering (`apps/api/app`)
Strict layers, do not bypass:
- `api/` — FastAPI routers, request validation, HTTP status. Thin; delegates to services.
- `services/` — business logic. `OrganizationService`, `ReviewService`, `ScrapeService`, `AnalysisService`. All take a SQLAlchemy `Session` in the constructor.
- `models/` — SQLAlchemy ORM models + `enums.py` (status/mode string enums shared across layers).
- `schemas/` — Pydantic request/response models.
- `scraper/` — scrapers (`yandex_public.py` Playwright, `yandex_auth.py` operator-auth, `yandex_http.py` browserless requests) + structured HTML parsing (BeautifulSoup, `parser.py`), isolated from the web layer.
- `analysis/` — pure, stdlib-only rule-based analytics (`sentiment.py`, `problems.py`, `analyzer.py`). No DB, no I/O, no external/LLM calls.

`core/config.py` is the single source of settings (pydantic-settings, reads `.env`). `core/database.py` exposes `get_db` (request-scoped dependency) and `SessionLocal` (used directly by background tasks).

### Scrape flow (the core of the product)
1. `POST /api/organizations/{id}/scrape` or `POST /api/scrape/all` creates a `ScrapeRun` (status `queued`) and schedules `_run_scrape_background` via FastAPI **BackgroundTasks** (deliberately no Celery — see constitution YAGNI principle). Background tasks open their **own** `SessionLocal`, not the request session.
2. `ScrapeService.execute_run` picks a scraper by mode:
   - `public` → `YandexPublicScraper` (headless Chromium, opens the "Отзывы" tab, scroll-loads reviews).
   - `operator_auth` → `YandexAuthScraper` using a saved Playwright storage-state file. If the session isn't `valid`, the run ends as `needs_manual_action` (operator must run login first) — it is **not** a failure.
   - `public_http` → `YandexHttpScraper` (feature 003): **browserless** requests + `?page=N` pagination, no Playwright. Delegates review extraction to `parse_reviews_from_html`; bot-protection/captcha → `needs_manual_action` + HTML debug artifact (no bypass). Has its own web page `/http-scraper`. Settings (`http_scrape_limit/max_pages/delay`) in `core/config.py`.
3. Parsed reviews are persisted by `ReviewService.upsert_reviews`. Each run records counts (`reviews_seen/inserted/updated`), timestamps, and status; failures save debug artifacts (screenshot + HTML paths).
4. Bulk `/scrape/all` creates one parent run plus a child `ScrapeRun` per organization. The parent's terminal status aggregates the children (feature 010): all failed → `failed`; no success but ≥1 `needs_manual_action` → `needs_manual_action`; otherwise `success`; parent counters are child sums.
5. Session login/check (`POST /api/scraper/yandex/login`, `/session/check`) run Playwright via BackgroundTasks too (feature 010): the endpoint sets `SessionStatus.pending` and returns 202 immediately; poll `GET /session` for the terminal state. A second request while `pending` is a no-op.

`/scrape/all` accepts `mode` directly; per-org scrape falls back to the org's `preferred_scrape_mode` when no mode is given.

### Background jobs (pages `/jobs` + `/jobs/runs/[id]`)
Four jobs, one row per `kind × platform` combination (`org_metrics`/`reviews` × `yandex`/`gis2`) in the `jobs` table; all four are seeded disabled but with a pre-wired cron (`org_metrics` 04:00, `reviews` 05:00 Europe/Moscow — metrics first so the review-count comparison sees fresh numbers), so flipping `is_enabled` immediately activates a nightly full-platform scrape. A run starts manually (`POST /api/jobs/{id}/run`, admin-only, 202) or by cron; either way `JobService.create_run` locks the job row (`with_for_update`) and rejects a second trigger with `JobAlreadyRunning` (surfaced as 409) while one is already `queued`/`running`. Cron is an in-process APScheduler (`JobScheduler`, `services/job_scheduler.py`) started in the FastAPI lifespan. `JOBS_SCHEDULER_ENABLED` defaults to `true` (see `.env.example`); `tests/conftest.py` forces it `false` for pytest. Standalone CLI scripts under `apps/api/scripts/` never import `app.main` or run the lifespan at all, so the scheduler never starts for them regardless of the flag — it isn't the flag that keeps CLI runs scheduler-free, it's that they never boot the FastAPI app. `JobRunner.execute` (`services/job_runner.py`) walks the platform's organizations strictly sequentially with a `time.sleep(options.delay_seconds)` pause between them (scrapers rate-limit), writing exactly one `JobRunItem` per organization. The run's terminal status aggregates the item statuses: all failed → `failed`; no success but ≥1 `needs_manual_action` → `needs_manual_action`; a mix of success and failure/manual → `partial`; otherwise `success` — and a mid-run crash (an exception outside the per-organization try/except) forces `failed` regardless of how many organizations already succeeded. The `org_metrics` job runs `MetricsService` (shared with `scripts/scrape_metrics.py`) per organization. The `reviews` job (feature 011) scrapes an organization when the platform's review count (`Organization.<platform>_review_count`) *differs in either direction* from the **non-removed** (`removed_at IS NULL`) count already scraped for that platform — higher = new reviews, lower = reviews deleted/disputed upstream; equal or unknown (`None`) skip with their own reason. Such a scrape always uses `public_http` (Yandex) / `twogis_api` (2GIS) — not the organization's `preferred_scrape_mode` — and requests uncapped pagination (`limit=math.inf`, `max_pages=ALL_REVIEWS_MAX_PAGES` from `scraper/types.py`, shared with the CLI's `--all-reviews`). Optional job option `force_full_every_days: N` (validated ≥1 in `JobUpdateRequest`) forces a scrape even when counters match if the org's last corroborated full pass (a `scrape_runs` row with `status=success AND full_pass`) is absent or older than N days — covers the "+1 added, −1 removed" blind spot; the forced decision lands in `JobRunItem.reason`. `job_runs`/`job_run_items` are retained 20 days; a separate APScheduler cron entry (`15 3 * * *`, fixed to `Europe/Moscow`) purges rows past that window nightly. `scrape_runs` itself is untouched by any of this — the `reviews` job links to it only via `job_run_items.scrape_run_id`.

### Deduplication (highest-impact invariant)
Reviews are deduped per organization by `content_hash` = SHA-256 of normalized `author_name | rating | review_date_text | review_text` (`scraper/normalize.py:build_review_hash`). On re-scrape, an existing hash updates `last_seen_at` (and fills `response_text` if newly present, and clears `removed_at` — a re-sighted review is present again, feature 011) instead of inserting. `upsert_reviews` (feature 010) preloads the batch's existing hashes in one query and wraps each insert in a SAVEPOINT (`begin_nested`): a concurrent-duplicate `IntegrityError` rolls back only that row and retries it as an update — earlier batch inserts survive and the run counters stay exact. Changing the hash inputs or normalization silently re-inserts every review — treat `build_review_hash` and `test_review_deduplication.py` as a contract.

### Removal tracking (feature 011, `specs/011-review-removal-sync/`)
`Review.removed_at` (nullable, never feeds the hash): NULL = present on the platform; set = a corroborated full pass no longer saw it. `ScrapeResult.full_pass` is set by the paginating scrapers (`yandex_http`, `twogis_api`) only when pagination was provably exhausted — no `limit`/`max_pages` cap hit, no page skipped over a transient error; Playwright scroll modes never set it. `ScrapeService._persist_scrape_result` then **corroborates** it against the org's stored platform counter (`run.full_pass = result.full_pass AND counter is not None AND seen >= counter`) because Yandex serves at most ~600 reviews over `?page=N` — exhaustion alone lies for bigger orgs (they simply never get a corroborated full pass and never mark removals). Only a corroborated full pass calls `ReviewService.mark_removed_missing` (scoped `UPDATE ... WHERE org+platform AND removed_at IS NULL AND content_hash NOT IN (seen)`). Zero-guard: a full pass with 0 reviews while non-removed rows exist and the counter ≠ 0 finalizes the run as `failed` with `error_code="empty_full_pass"` (parser-regression suspicion) — mass-marking to zero is allowed only when the counter corroborates 0. Review list endpoints take `removed=active|removed|all` (default `active` — removed rows are hidden from default lists and from the job's count comparison; `ReviewService.count_present` is the comparison figure); the org page has a "показать удалённые" toggle. Tests: `test_review_removal.py`, `test_scraper_full_pass.py`, `test_job_runner_reviews.py` — treat the "partial/uncorroborated pass never marks" rule as a contract.

### Review analytics (feature 002, `analysis/` + `AnalysisService`)
Deterministic, local, rule-based (constitution Principle VI — no LLM/external calls). `ReviewAnalyzer.analyze(text, rating)` returns sentiment (label/score/confidence), problem categories (8-category taxonomy with severity + context), and a rating↔sentiment mismatch flag. `ReviewService.upsert_reviews` runs analysis **after** `build_review_hash` (analysis fields are additive columns + `problems` JSONB; they never feed the dedup hash). Backfill via `POST /api/organizations/{id}/analyze`; per-org aggregate via `GET /api/organizations/{id}/analytics`. Analysis must degrade safely (empty/garbage text → neutral/empty, never raise) and stays idempotent. JSONB column uses `JSON().with_variant(JSONB, "postgresql")` so SQLite-backed tests work.

### Status enums (`models/enums.py`)
`ScrapeMode` (public | operator_auth | public_http), `ScrapeRunStatus`, `OrganizationScrapeStatus`, `SessionStatus`. `needs_manual_action` is a first-class outcome (captcha/2FA/expired session/bot-wall), distinct from `failed`. `SessionStatus.pending` (feature 010) marks an in-flight background login/check. Captcha/bot markers live in one shared module `scraper/markers.py` (`BOT_MARKERS`); `yandex_public` re-exports it as `CAPTCHA_MARKERS`, `twogis_api` extends it with 2GIS-specific phrases — add markers there, not per-scraper. Note: in the real DB (migration 0001) all three `scrape_mode` columns share one Postgres type `scrape_mode_enum` — the differing `name=` in the ORM models only matter for SQLite test backends. Adding a mode = `ALTER TYPE scrape_mode_enum ADD VALUE` (see migration 0003).

### Frontend (`apps/web`)
Next.js App Router (`app/`). All backend calls go through `lib/api.ts` (single `request<T>` wrapper, `cache: "no-store"`); types mirror the API in `lib/types.ts`. Base URL from `NEXT_PUBLIC_API_URL`. Pages are server components reading the API; tables/forms are client components under `components/`.

## Constraints (enforced by `.specify/memory/constitution.md`)

This is a Spec Kit project: changes flow constitution → specify → plan → tasks → implement. Features: `specs/001-yandex-reviews-mvp/` (MVP), `specs/002-review-analytics/` (analytics + structured parsing), `specs/003-http-scraper/` (browserless `public_http` mode + page). Constitution is at **v1.1.0** — Principle VI permits deterministic local analytics; LLM/external-ML analysis stays out of scope. The plan in `specs/<feature>/plan.md` is the source of truth for stack/structure.

Hard rules — do not violate without a constitution amendment:
- **Read-only.** Collect/display Yandex reviews only. Never publish, edit, or delete replies on Yandex. Stored business responses are display-only.
- **Out of scope:** app auth/roles, posting replies, other providers (Google/2GIS), LLM features, real-time notifications (WebSocket/email), Celery/queues, forced captcha bypass. Don't add these.
- **Scraper debuggability.** Every attempt produces a `ScrapeRun` with status/timestamps/counts. Failures must save debug artifacts. Captcha/2FA/access challenges surface as `needs_manual_action`, never silent retries or generic failures.
- **Critical-path tests required before merge:** dedup, normalization/hash, org & scrape-run API contracts, scrape-result persistence. Full per-file TDD is not required.
- **Credentials.** Yandex operator creds live only in env vars. Playwright storage-state files and the `.local/` dir are gitignored and must stay out of logs and API responses.

<!-- SPECKIT START -->
For additional context about technologies to be used, project structure,
shell commands, and other important information, read the current plan:
specs/001-yandex-reviews-mvp/plan.md

Also available:
- Feature spec: specs/001-yandex-reviews-mvp/spec.md
- Data model: specs/001-yandex-reviews-mvp/data-model.md
- API contracts: specs/001-yandex-reviews-mvp/contracts/
- Quickstart: specs/001-yandex-reviews-mvp/quickstart.md
- Tasks: specs/001-yandex-reviews-mvp/tasks.md
- Reference notes: docs/plans/2026-06-14-yandex-reviews-mvp.md
<!-- SPECKIT END -->
