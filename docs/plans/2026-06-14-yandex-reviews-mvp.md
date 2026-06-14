# Yandex Reviews MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox `- [ ]`) syntax for tracking.

**Goal:** Build a minimal internal dashboard that collects Yandex Maps organization reviews through Playwright and displays organizations, reviews, scrape status, and scrape errors without application auth, roles, or review replies.

**Architecture:** The MVP has a Next.js dashboard, a FastAPI backend, PostgreSQL storage, and a Playwright scraper module. The scraper supports two collection modes: public page scraping without login and operator-auth scraping through a saved Playwright browser session. The product is read-only: it collects and displays reviews, but does not publish replies to Yandex.

**Tech Stack:** Next.js, TypeScript, TailwindCSS, shadcn/ui, FastAPI, Python Playwright, SQLAlchemy, Alembic, PostgreSQL, Docker Compose, pytest, Playwright E2E.

---

## 1. MVP Scope

### In Scope

- Organization board with a list of Yandex Maps organizations.

- Organization detail page with reviews from Yandex Maps.

- Global reviews feed across all organizations.

- Manual organization creation by Yandex Maps URL.

- Manual scrape trigger for one organization.

- Manual scrape trigger for all organizations.

- Public Playwright scraping directly from the Yandex Maps organization page.

- Operator-auth Playwright scraping using operator login and password.

- Saved Playwright authenticated session state.

- Scrape run history and visible scrape errors.

- Deduplication of already collected reviews.

- Screenshots and HTML snapshots for failed scrape runs.

### Out of Scope

- Application login and roles.

- Replies to reviews.

- Google Maps and 2GIS.

- LLM review analysis.

- LLM response generation.

- WebSocket notifications.

- Email notifications.

- Franchisee reports.

- TimescaleDB.

- Full Celery-based background pipeline.

- Anti-captcha or forced captcha bypass.

### Success Criteria

- The user can add at least 5 Yandex Maps organization URLs.

- The user can run public scraping for one organization and see collected reviews.

- The user can run operator-auth scraping and see collected reviews.

- Duplicate reviews are not inserted twice.

- Each scrape run records status, start time, finish time, error text, and counts.

- Failed scraper runs produce a screenshot and HTML snapshot path for debugging.

- The dashboard clearly shows when the last successful scrape happened.

---

## 2. Product Workflow

1. User opens the dashboard.

2. User adds a Yandex Maps organization URL.

3. Backend stores the organization with status `pending`.

4. User clicks `Обновить` for the organization.

5. Backend starts a scrape run in either `public` or `operator_auth` mode.

6. Scraper opens the organization page with Playwright.

7. Scraper extracts organization metadata and reviews.

8. Backend stores new reviews and updates the scrape run status.

9. UI refreshes the organization row and review list.

10. If scraping fails, UI shows the failure reason and links to saved debug artifacts.

---

## 3. Data Model

### `organizations`

Stores tracked Yandex Maps organizations.

Required fields:

- `id`: UUID primary key.

- `name`: nullable text; filled by scraper when available.

- `yandex_url`: original URL provided by user.

- `normalized_url`: canonical URL after cleanup.

- `external_id`: nullable Yandex identifier if parsed from URL/page.

- `address`: nullable text.

- `rating`: nullable numeric.

- `review_count`: nullable integer.

- `preferred_scrape_mode`: enum: `public`, `operator_auth`.

- `last_successful_scrape_at`: nullable timestamp.

- `last_scrape_status`: enum: `pending`, `running`, `success`, `failed`, `needs_manual_action`.

- `created_at`: timestamp.

- `updated_at`: timestamp.

### `reviews`

Stores collected Yandex reviews.

Required fields:

- `id`: UUID primary key.

- `organization_id`: foreign key to `organizations`.

- `source`: fixed value `yandex_maps`.

- `scrape_mode`: enum: `public`, `operator_auth`.

- `external_review_id`: nullable text if found.

- `author_name`: nullable text.

- `rating`: integer from 1 to 5.

- `review_text`: text.

- `review_date_text`: original date string from Yandex.

- `review_date`: nullable parsed date.

- `response_text`: nullable text, only if visible on page.

- `content_hash`: stable hash used for deduplication.

- `first_seen_at`: timestamp.

- `last_seen_at`: timestamp.

Deduplication rule:

```text

organization_id + content_hash must be unique

```

`content_hash` is generated from:

```text

normalize(author_name) + "|" + rating + "|" + normalize(review_date_text) + "|" + normalize(review_text)

```

### `scrape_runs`

Stores one execution attempt.

Required fields:

- `id`: UUID primary key.

- `organization_id`: nullable foreign key. Null means "all organizations" parent run.

- `mode`: enum: `public`, `operator_auth`.

- `status`: enum: `queued`, `running`, `success`, `failed`, `needs_manual_action`.

- `started_at`: timestamp.

- `finished_at`: nullable timestamp.

- `reviews_seen`: integer.

- `reviews_inserted`: integer.

- `reviews_updated`: integer.

- `error_code`: nullable text.

- `error_message`: nullable text.

- `debug_screenshot_path`: nullable text.

- `debug_html_path`: nullable text.

### `scraper_sessions`

Stores metadata for authenticated Playwright sessions.

Required fields:

- `id`: UUID primary key.

- `provider`: fixed value `yandex`.

- `storage_state_path`: path to encrypted or private local file.

- `status`: enum: `missing`, `valid`, `expired`, `needs_manual_action`.

- `last_login_at`: nullable timestamp.

- `last_checked_at`: nullable timestamp.

---

## 4. API Contract

### Organization API

- `GET /api/organizations`

  - Returns organizations with last scrape summary.

- `POST /api/organizations`

  - Body: `{ "yandex_url": "...", "preferred_scrape_mode": "public" }`

  - Creates an organization.

- `GET /api/organizations/{organization_id}`

  - Returns one organization.

- `PATCH /api/organizations/{organization_id}`

  - Updates preferred scrape mode or display name.

- `DELETE /api/organizations/{organization_id}`

  - Soft-delete or hard-delete can be decided during implementation; MVP can hard-delete if no compliance requirement exists.

### Reviews API

- `GET /api/reviews`

  - Query filters: `organization_id`, `rating`, `date_from`, `date_to`, `new_only`.

- `GET /api/organizations/{organization_id}/reviews`

  - Paginated reviews for one organization.

### Scraper API

- `POST /api/organizations/{organization_id}/scrape`

  - Body: `{ "mode": "public" }` or `{ "mode": "operator_auth" }`

  - Starts scrape for one organization.

- `POST /api/scrape/all`

  - Body: `{ "mode": "public" }` or `{ "mode": "operator_auth" }`

  - Starts scrape for all organizations.

- `GET /api/scrape-runs`

  - Returns recent scrape runs.

- `GET /api/scrape-runs/{run_id}`

  - Returns run details.

### Auth Session API

- `POST /api/scraper/yandex/login`

  - Starts operator login using environment credentials.

- `GET /api/scraper/yandex/session`

  - Returns current session status without exposing secrets.

- `POST /api/scraper/yandex/session/check`

  - Checks whether saved session is still valid.

---

## 5. File Structure

```text

.

├── apps

│   ├── api

│   │   ├── app

│   │   │   ├── api

│   │   │   │   ├── [organizations.py](http://organizations.py)

│   │   │   │   ├── [reviews.py](http://reviews.py)

│   │   │   │   ├── scrape_[runs.py](http://runs.py)

│   │   │   │   └── scraper_[sessions.py](http://sessions.py)

│   │   │   ├── core

│   │   │   │   ├── [config.py](http://config.py)

│   │   │   │   └── [database.py](http://database.py)

│   │   │   ├── models

│   │   │   │   ├── [organization.py](http://organization.py)

│   │   │   │   ├── [review.py](http://review.py)

│   │   │   │   ├── scrape_[run.py](http://run.py)

│   │   │   │   └── scraper_[session.py](http://session.py)

│   │   │   ├── schemas

│   │   │   │   ├── [organization.py](http://organization.py)

│   │   │   │   ├── [review.py](http://review.py)

│   │   │   │   ├── scrape_[run.py](http://run.py)

│   │   │   │   └── scraper_[session.py](http://session.py)

│   │   │   ├── scraper

│   │   │   │   ├── yandex_[public.py](http://public.py)

│   │   │   │   ├── yandex_[auth.py](http://auth.py)

│   │   │   │   ├── [parser.py](http://parser.py)

│   │   │   │   ├── [normalize.py](http://normalize.py)

│   │   │   │   └── debug_[artifacts.py](http://artifacts.py)

│   │   │   ├── services

│   │   │   │   ├── organization_[service.py](http://service.py)

│   │   │   │   ├── review_[service.py](http://service.py)

│   │   │   │   └── scrape_[service.py](http://service.py)

│   │   │   └── [main.py](http://main.py)

│   │   ├── alembic

│   │   ├── tests

│   │   │   ├── test_review_[deduplication.py](http://deduplication.py)

│   │   │   ├── test_yandex_[normalize.py](http://normalize.py)

│   │   │   ├── test_organizations_[api.py](http://api.py)

│   │   │   └── test_scrape_runs_[api.py](http://api.py)

│   │   └── pyproject.toml

│   └── web

│       ├── app

│       │   ├── organizations

│       │   │   ├── page.tsx

│       │   │   └── [id]

│       │   │       └── page.tsx

│       │   ├── reviews

│       │   │   └── page.tsx

│       │   ├── scrape-runs

│       │   │   └── page.tsx

│       │   ├── layout.tsx

│       │   └── page.tsx

│       ├── components

│       │   ├── organization-form.tsx

│       │   ├── organizations-table.tsx

│       │   ├── reviews-table.tsx

│       │   ├── scrape-run-status.tsx

│       │   └── mode-select.tsx

│       ├── lib

│       │   ├── api.ts

│       │   └── types.ts

│       └── tests

│           └── yandex-reviews-mvp.spec.ts

├── docker-compose.yml

├── .env.example

└── [README.md](http://README.md)

```

---

## 6. Implementation Tasks

### Task 1: Repository Scaffold

**Files:**

- Create: `apps/api/pyproject.toml`

- Create: `apps/api/app/main.py`

- Create: `apps/api/app/core/config.py`

- Create: `apps/api/app/core/database.py`

- Create: `apps/web/package.json`

- Create: `docker-compose.yml`

- Create: `.env.example`

- Create: `README.md`

- [ ] Create FastAPI project under `apps/api`.

- [ ] Create Next.js project under `apps/web`.

- [ ] Add Docker Compose services: `postgres`, `api`, `web`.

- [ ] Add `.env.example` with non-secret variable names:

```text

DATABASE_URL=postgresql+psycopg://postgres:[postgres@localhost:5432](mailto:postgres@localhost:5432)/yandex_reviews

YANDEX_OPERATOR_LOGIN=

YANDEX_OPERATOR_PASSWORD=

YANDEX_STORAGE_STATE_PATH=.local/yandex-storage-state.json

SCRAPER_DEBUG_DIR=.local/scraper-debug

```

- [ ] Add README with local startup commands.

- [ ] Verify that `GET /health` returns `{ "status": "ok" }`.

### Task 2: Database Models and Migrations

**Files:**

- Create: `apps/api/app/models/organization.py`

- Create: `apps/api/app/models/review.py`

- Create: `apps/api/app/models/scrape_run.py`

- Create: `apps/api/app/models/scraper_session.py`

- Create: `apps/api/alembic/versions/0001_initial.py`

- Test: `apps/api/tests/test_review_deduplication.py`

- [ ] Define SQLAlchemy models for organizations, reviews, scrape runs, and scraper sessions.

- [ ] Add enum values exactly as listed in the data model section.

- [ ] Add unique constraint on `reviews.organization_id + reviews.content_hash`.

- [ ] Add migration `0001_initial.py`.

- [ ] Add test proving duplicate reviews are not inserted twice.

- [ ] Run:

```bash

cd apps/api

pytest tests/test_review_[deduplication.py](http://deduplication.py) -v

```

Expected: all tests pass.

### Task 3: Review Normalization

**Files:**

- Create: `apps/api/app/scraper/normalize.py`

- Test: `apps/api/tests/test_yandex_normalize.py`

- [ ] Implement `normalize_text(value: str | None) -> str`.

- [ ] Implement `build_review_hash(author_name, rating, review_date_text, review_text) -> str`.

- [ ] Normalize whitespace, trim text, lowercase author and date fields, preserve Russian text.

- [ ] Add tests for whitespace, empty author, same review with different spacing, and different ratings.

- [ ] Run:

```bash

cd apps/api

pytest tests/test_yandex_[normalize.py](http://normalize.py) -v

```

Expected: all tests pass.

### Task 4: Organization API

**Files:**

- Create: `apps/api/app/schemas/organization.py`

- Create: `apps/api/app/services/organization_service.py`

- Create: `apps/api/app/api/organizations.py`

- Modify: `apps/api/app/main.py`

- Test: `apps/api/tests/test_organizations_api.py`

- [ ] Implement `POST /api/organizations`.

- [ ] Implement `GET /api/organizations`.

- [ ] Implement `GET /api/organizations/{organization_id}`.

- [ ] Implement `PATCH /api/organizations/{organization_id}`.

- [ ] Implement `DELETE /api/organizations/{organization_id}`.

- [ ] Validate that `yandex_url` starts with `https://yandex.` or `https://yandex.ru/` or `https://yandex.com/`.

- [ ] Add API tests for create, list, update mode, and delete.

- [ ] Run:

```bash

cd apps/api

pytest tests/test_organizations_[api.py](http://api.py) -v

```

Expected: all tests pass.

### Task 5: Reviews API

**Files:**

- Create: `apps/api/app/schemas/review.py`

- Create: `apps/api/app/services/review_service.py`

- Create: `apps/api/app/api/reviews.py`

- Modify: `apps/api/app/main.py`

- [ ] Implement `GET /api/reviews`.

- [ ] Implement `GET /api/organizations/{organization_id}/reviews`.

- [ ] Add pagination with `limit` and `offset`.

- [ ] Add filters for `organization_id`, `rating`, `date_from`, `date_to`, `new_only`.

- [ ] Sort reviews by `review_date desc nulls last`, then `first_seen_at desc`.

### Task 6: Scrape Run API

**Files:**

- Create: `apps/api/app/schemas/scrape_run.py`

- Create: `apps/api/app/services/scrape_service.py`

- Create: `apps/api/app/api/scrape_runs.py`

- Modify: `apps/api/app/main.py`

- Test: `apps/api/tests/test_scrape_runs_api.py`

- [ ] Implement `POST /api/organizations/{organization_id}/scrape`.

- [ ] Implement `POST /api/scrape/all`.

- [ ] Implement `GET /api/scrape-runs`.

- [ ] Implement `GET /api/scrape-runs/{run_id}`.

- [ ] For MVP, run scrape in a FastAPI background task.

- [ ] Ensure each scrape run updates from `queued` to `running` to final status.

- [ ] Add API tests for scrape run creation and listing.

### Task 7: Public Yandex Playwright Scraper

**Files:**

- Create: `apps/api/app/scraper/yandex_public.py`

- Create: `apps/api/app/scraper/parser.py`

- Create: `apps/api/app/scraper/debug_artifacts.py`

- [ ] Implement public page open by organization URL.

- [ ] Wait for initial page content.

- [ ] Extract organization name when visible.

- [ ] Extract rating when visible.

- [ ] Open reviews area if the page requires a click.

- [ ] Scroll reviews panel until either no new reviews appear or max scroll count is reached.

- [ ] Extract author, rating, date text, review text, and visible business response text.

- [ ] Save screenshot and HTML snapshot on failure.

- [ ] Return structured scraper result to `scrape_service`.

Operational limits:

- Max page load wait: 30 seconds.

- Max review panel scrolls per organization: 40.

- Delay between scrolls: 800-1500 ms.

- Failure after captcha or access challenge: `needs_manual_action`.

### Task 8: Operator Auth Playwright Scraper

**Files:**

- Create: `apps/api/app/scraper/yandex_auth.py`

- Create: `apps/api/app/schemas/scraper_session.py`

- Create: `apps/api/app/api/scraper_sessions.py`

- Modify: `apps/api/app/main.py`

- [ ] Read `YANDEX_OPERATOR_LOGIN` and `YANDEX_OPERATOR_PASSWORD` from environment.

- [ ] Implement login flow in headed mode for local debugging and headless mode for server execution.

- [ ] Save Playwright `storage_state` to `YANDEX_STORAGE_STATE_PATH`.

- [ ] Implement session check endpoint.

- [ ] If login requires captcha, 2FA, or manual confirmation, set session status to `needs_manual_action`.

- [ ] Reuse public scraper extraction logic after authenticated browser context is ready.

- [ ] Never return password, cookies, or storage state content through the API.

Security requirements:

- Do not commit `.local/yandex-storage-state.json`.

- Do not log operator password.

- Do not expose cookies in API responses.

- Add `.local/` to `.gitignore`.

### Task 9: Frontend Organization Board

**Files:**

- Create: `apps/web/app/page.tsx`

- Create: `apps/web/app/organizations/page.tsx`

- Create: `apps/web/components/organization-form.tsx`

- Create: `apps/web/components/organizations-table.tsx`

- Create: `apps/web/components/mode-select.tsx`

- Create: `apps/web/lib/api.ts`

- Create: `apps/web/lib/types.ts`

- [ ] Implement API client functions.

- [ ] Implement add-organization form.

- [ ] Implement organizations table.

- [ ] Show name, URL, rating, review count, preferred mode, last scrape status, last successful scrape date.

- [ ] Add `Обновить` button per organization.

- [ ] Add mode selector: `public` and `operator_auth`.

- [ ] Add global `Обновить все` button.

### Task 10: Frontend Reviews Views

**Files:**

- Create: `apps/web/app/organizations/[id]/page.tsx`

- Create: `apps/web/app/reviews/page.tsx`

- Create: `apps/web/components/reviews-table.tsx`

- [ ] Implement organization detail page.

- [ ] Implement global reviews page.

- [ ] Show author, rating, date, text, scrape mode, first seen date.

- [ ] Add filters for organization, rating, date range, and new-only.

- [ ] Add empty state when no reviews exist.

### Task 11: Frontend Scrape Run History

**Files:**

- Create: `apps/web/app/scrape-runs/page.tsx`

- Create: `apps/web/components/scrape-run-status.tsx`

- [ ] Implement scrape runs page.

- [ ] Show run mode, status, started time, duration, seen count, inserted count, error message.

- [ ] Show debug artifact paths for failed runs.

- [ ] Make `needs_manual_action` visually distinct from generic failure.

### Task 12: E2E and Verification

**Files:**

- Create: `apps/web/tests/yandex-reviews-mvp.spec.ts`

- Modify: `README.md`

- [ ] Add E2E test that opens organization board.

- [ ] Add E2E test that creates an organization with a test URL against mocked API or seeded DB.

- [ ] Add E2E test that opens organization details and sees reviews.

- [ ] Document local verification commands:

```bash

docker compose up --build

cd apps/api

pytest -v

cd ../web

npm run lint

npm run test:e2e

```

Expected: API tests pass, frontend lint passes, E2E smoke tests pass.

---

## 7. Manual QA Checklist

- [ ] Add organization by Yandex Maps URL.

- [ ] Run public scrape.

- [ ] Confirm organization row updates after scrape.

- [ ] Open organization page and confirm reviews are visible.

- [ ] Run public scrape again and confirm duplicates are not added.

- [ ] Configure operator credentials in `.env`.

- [ ] Run operator login.

- [ ] Confirm session status is `valid`.

- [ ] Run operator-auth scrape.

- [ ] Confirm auth scrape stores reviews with `scrape_mode = operator_auth`.

- [ ] Force a bad URL and confirm scrape run fails with readable error.

- [ ] Force expired session and confirm status becomes `needs_manual_action`.

---

## 8. Delivery Milestones

### Milestone 1: Data Backbone

Deliverables:

- API scaffold.

- DB schema.

- Organization CRUD.

- Reviews API.

- Scrape run records.

Acceptance:

- API tests pass.

- Organizations and reviews can be created and listed through API.

### Milestone 2: Public Scraper Vertical Slice

Deliverables:

- Public Playwright scraper.

- One-organization scrape endpoint.

- Review persistence with deduplication.

- Debug artifacts on failure.

Acceptance:

- One real organization URL can be scraped.

- Repeated scrape does not duplicate reviews.

### Milestone 3: Dashboard

Deliverables:

- Organization board.

- Organization detail page.

- Reviews feed.

- Scrape run history.

Acceptance:

- User can add an organization, run scrape, and inspect reviews from the browser UI.

### Milestone 4: Operator Auth Mode

Deliverables:

- Operator login flow.

- Saved Playwright session.

- Session status API.

- Authenticated scrape mode.

Acceptance:

- Authenticated scrape works for at least one organization.

- Expired login, captcha, or 2FA is reported as `needs_manual_action`.

---

## 9. Implementation Notes

- Prefer stable selectors when possible, but expect Yandex Maps DOM to change.

- Keep scraper parsing isolated from persistence so parser tests can use saved HTML fixtures later.

- Do not attempt to bypass captcha.

- Keep scrape speed conservative to reduce blocking risk.

- Store raw debug artifacts only for failed runs to avoid uncontrolled disk growth.

- Add `.local/` and Playwright artifacts to `.gitignore`.

- Use manual scrape buttons first; add scheduled scraping only after the MVP proves stable.

