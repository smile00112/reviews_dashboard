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
- `scraper/` — Playwright scrapers + structured HTML parsing (BeautifulSoup, `parser.py`), isolated from the web layer.
- `analysis/` — pure, stdlib-only rule-based analytics (`sentiment.py`, `problems.py`, `analyzer.py`). No DB, no I/O, no external/LLM calls.

`core/config.py` is the single source of settings (pydantic-settings, reads `.env`). `core/database.py` exposes `get_db` (request-scoped dependency) and `SessionLocal` (used directly by background tasks).

### Scrape flow (the core of the product)
1. `POST /api/organizations/{id}/scrape` or `POST /api/scrape/all` creates a `ScrapeRun` (status `queued`) and schedules `_run_scrape_background` via FastAPI **BackgroundTasks** (deliberately no Celery — see constitution YAGNI principle). Background tasks open their **own** `SessionLocal`, not the request session.
2. `ScrapeService.execute_run` picks a scraper by mode:
   - `public` → `YandexPublicScraper` (headless Chromium, opens the "Отзывы" tab, scroll-loads reviews).
   - `operator_auth` → `YandexAuthScraper` using a saved Playwright storage-state file. If the session isn't `valid`, the run ends as `needs_manual_action` (operator must run login first) — it is **not** a failure.
3. Parsed reviews are persisted by `ReviewService.upsert_reviews`. Each run records counts (`reviews_seen/inserted/updated`), timestamps, and status; failures save debug artifacts (screenshot + HTML paths).
4. Bulk `/scrape/all` creates one parent run plus a child `ScrapeRun` per organization.

`/scrape/all` accepts `mode` directly; per-org scrape falls back to the org's `preferred_scrape_mode` when no mode is given.

### Deduplication (highest-impact invariant)
Reviews are deduped per organization by `content_hash` = SHA-256 of normalized `author_name | rating | review_date_text | review_text` (`scraper/normalize.py:build_review_hash`). On re-scrape, an existing hash updates `last_seen_at` (and fills `response_text` if newly present) instead of inserting. `upsert_reviews` also catches `IntegrityError` and retries as an update to survive races. Changing the hash inputs or normalization silently re-inserts every review — treat `build_review_hash` and `test_review_deduplication.py` as a contract.

### Review analytics (feature 002, `analysis/` + `AnalysisService`)
Deterministic, local, rule-based (constitution Principle VI — no LLM/external calls). `ReviewAnalyzer.analyze(text, rating)` returns sentiment (label/score/confidence), problem categories (8-category taxonomy with severity + context), and a rating↔sentiment mismatch flag. `ReviewService.upsert_reviews` runs analysis **after** `build_review_hash` (analysis fields are additive columns + `problems` JSONB; they never feed the dedup hash). Backfill via `POST /api/organizations/{id}/analyze`; per-org aggregate via `GET /api/organizations/{id}/analytics`. Analysis must degrade safely (empty/garbage text → neutral/empty, never raise) and stays idempotent. JSONB column uses `JSON().with_variant(JSONB, "postgresql")` so SQLite-backed tests work.

### Status enums (`models/enums.py`)
`ScrapeMode` (public | operator_auth), `ScrapeRunStatus`, `OrganizationScrapeStatus`, `SessionStatus`. `needs_manual_action` is a first-class outcome (captcha/2FA/expired session), distinct from `failed`. Captcha detection lives in `YandexPublicScraper.CAPTCHA_MARKERS`.

### Frontend (`apps/web`)
Next.js App Router (`app/`). All backend calls go through `lib/api.ts` (single `request<T>` wrapper, `cache: "no-store"`); types mirror the API in `lib/types.ts`. Base URL from `NEXT_PUBLIC_API_URL`. Pages are server components reading the API; tables/forms are client components under `components/`.

## Constraints (enforced by `.specify/memory/constitution.md`)

This is a Spec Kit project: changes flow constitution → specify → plan → tasks → implement. Features: `specs/001-yandex-reviews-mvp/` (MVP) and `specs/002-review-analytics/` (analytics + structured parsing). Constitution is at **v1.1.0** — Principle VI permits deterministic local analytics; LLM/external-ML analysis stays out of scope. The plan in `specs/<feature>/plan.md` is the source of truth for stack/structure.

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
