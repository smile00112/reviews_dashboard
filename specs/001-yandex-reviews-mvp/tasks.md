# Tasks: Yandex Reviews MVP

**Input**: Design documents from `/specs/001-yandex-reviews-mvp/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Organization**: Tasks grouped by user story for independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: User story label (US1–US5)

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Monorepo scaffold, Docker, health endpoint

- [x] T001 Create `apps/api/pyproject.toml` with FastAPI, SQLAlchemy, Alembic, Playwright, pytest dependencies
- [x] T002 [P] Create `apps/web/package.json` with Next.js, TypeScript, TailwindCSS, shadcn/ui
- [x] T003 [P] Create `docker-compose.yml` with postgres, api, web services
- [x] T004 [P] Create `.env.example` with DATABASE_URL, YANDEX_OPERATOR_LOGIN, YANDEX_OPERATOR_PASSWORD, YANDEX_STORAGE_STATE_PATH, SCRAPER_DEBUG_DIR
- [x] T005 Create `apps/api/app/main.py` with FastAPI app and `GET /health` returning `{"status":"ok"}`
- [x] T006 [P] Create `apps/api/app/core/config.py` loading env settings via pydantic-settings
- [x] T007 [P] Create `apps/api/app/core/database.py` with SQLAlchemy engine and session factory
- [x] T008 Create root `README.md` with Docker Compose and local dev startup commands

**Checkpoint**: `docker compose up --build` starts; `GET /health` returns ok

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Database schema, normalization, deduplication — MUST complete before user stories

**⚠️ CRITICAL**: No user story work until this phase is complete

- [x] T009 Create SQLAlchemy models in `apps/api/app/models/organization.py`, `review.py`, `scrape_run.py`, `scraper_session.py` per data-model.md enums and fields
- [x] T010 Initialize Alembic in `apps/api/alembic/` and create `apps/api/alembic/versions/0001_initial.py` with unique constraint on `(organization_id, content_hash)`
- [x] T011 [P] Create Pydantic schemas in `apps/api/app/schemas/` for organization, review, scrape_run, scraper_session
- [x] T012 Implement `normalize_text` and `build_review_hash` in `apps/api/app/scraper/normalize.py` per data-model.md hash algorithm
- [x] T013 Create `apps/api/tests/test_yandex_normalize.py` covering whitespace, empty author, spacing variants, different ratings
- [x] T014 Create `apps/api/tests/test_review_deduplication.py` proving duplicate reviews are not inserted twice
- [x] T015 Wire database session dependency and router includes in `apps/api/app/main.py`
- [x] T016 Add `.local/` to `.gitignore` for storage state and debug artifacts
- [x] T017 Run migrations: `alembic upgrade head` in `apps/api`
- [x] T018 Run pytest: `pytest tests/test_yandex_normalize.py tests/test_review_deduplication.py -v` — all pass

**Checkpoint**: Schema migrated; normalize and dedup tests green

---

## Phase 3: User Story 1 — Organization Board (Priority: P1) 🎯 MVP

**Goal**: Add/list/update/delete organizations; API ready for dashboard board

**Independent Test**: POST organization URL → GET list shows org with `pending` status

### Implementation for User Story 1

- [x] T019 [US1] Implement `OrganizationService` CRUD and URL validation in `apps/api/app/services/organization_service.py`
- [x] T020 [US1] Implement organization router in `apps/api/app/api/organizations.py` per `contracts/organizations-api.md`
- [x] T021 [US1] Register organizations router in `apps/api/app/main.py`
- [x] T022 [US1] Create `apps/api/tests/test_organizations_api.py` for create, list, update mode, delete
- [x] T023 [P] [US1] Create `apps/web/lib/types.ts` with Organization TypeScript types
- [x] T024 [P] [US1] Create `apps/web/lib/api.ts` with fetch helpers for organization endpoints
- [x] T025 [US1] Create `apps/web/components/mode-select.tsx` for public/operator_auth selection
- [x] T026 [US1] Create `apps/web/components/organization-form.tsx` add-organization form
- [x] T027 [US1] Create `apps/web/components/organizations-table.tsx` showing name, URL, rating, review count, mode, last status, last success date
- [x] T028 [US1] Create `apps/web/app/organizations/page.tsx` and redirect `apps/web/app/page.tsx` to organizations board

**Checkpoint**: Organization CRUD via API and UI; pytest org API tests pass

---

## Phase 4: User Story 2 — Public Review Collection (Priority: P1) 🎯 MVP

**Goal**: Public Playwright scrape, persist reviews, trigger from UI, org detail page

**Independent Test**: Trigger public scrape → reviews on detail page; re-scrape no duplicates

### Implementation for User Story 2

- [x] T029 [US2] Implement `debug_artifacts.py` in `apps/api/app/scraper/debug_artifacts.py` for screenshot and HTML snapshot on failure
- [x] T030 [US2] Implement review parser in `apps/api/app/scraper/parser.py` extracting author, rating, date, text, response
- [x] T031 [US2] Implement public scraper in `apps/api/app/scraper/yandex_public.py` with 30s load wait, 40 max scrolls, 800–1500ms scroll delay
- [x] T032 [US2] Implement `ReviewService` upsert with dedup in `apps/api/app/services/review_service.py`
- [x] T033 [US2] Implement `ScrapeService` with BackgroundTasks lifecycle (queued→running→final) in `apps/api/app/services/scrape_service.py`
- [x] T034 [US2] Implement scrape endpoints in `apps/api/app/api/scrape_runs.py` per `contracts/scrape-api.md` (single-org scrape + list runs)
- [x] T035 [US2] Implement org reviews endpoint in `apps/api/app/api/reviews.py` for `GET /api/organizations/{id}/reviews`
- [x] T036 [US2] Create `apps/api/tests/test_scrape_runs_api.py` for scrape creation and listing
- [x] T037 [US2] Add **Обновить** button and mode selector per row in `apps/web/components/organizations-table.tsx` calling scrape API
- [x] T038 [US2] Add global **Обновить все** button on `apps/web/app/organizations/page.tsx` calling `POST /api/scrape/all`
- [x] T039 [P] [US2] Create `apps/web/components/reviews-table.tsx` for review list display
- [x] T040 [US2] Create `apps/web/app/organizations/[id]/page.tsx` organization detail with reviews table
- [x] T041 [US2] Map captcha/access challenge to `needs_manual_action` in `apps/api/app/scraper/yandex_public.py`
- [x] T042 [US2] Verify public scrape E2E manually per quickstart.md Milestone 2

**Checkpoint**: Public scrape works for real URL; dedup on re-scrape; org detail shows reviews

---

## Phase 5: User Story 3 — Global Reviews Feed (Priority: P2)

**Goal**: Cross-organization reviews page with filters

**Independent Test**: Reviews from 2+ orgs visible; filters by org and rating work

### Implementation for User Story 3

- [x] T043 [US3] Implement `GET /api/reviews` with pagination and filters (organization_id, rating, date_from, date_to, new_only) in `apps/api/app/api/reviews.py`
- [x] T044 [US3] Extend `ReviewService` query methods in `apps/api/app/services/review_service.py` for global feed sorting
- [x] T045 [US3] Add reviews API helpers to `apps/web/lib/api.ts`
- [x] T046 [US3] Create `apps/web/app/reviews/page.tsx` global reviews page with filter controls
- [x] T047 [US3] Wire filter UI to query params in `apps/web/app/reviews/page.tsx`
- [x] T048 [US3] Add empty state when no reviews in `apps/web/components/reviews-table.tsx`

**Checkpoint**: Global feed with filters; empty state when no data

---

## Phase 6: User Story 4 — Scrape History & Failure Debugging (Priority: P2)

**Goal**: Scrape runs history page with errors and debug artifact paths

**Independent Test**: Failed scrape shows error + artifact paths; `needs_manual_action` visually distinct

### Implementation for User Story 4

- [x] T049 [US4] Implement `GET /api/scrape-runs/{run_id}` in `apps/api/app/api/scrape_runs.py`
- [x] T050 [P] [US4] Create `apps/web/components/scrape-run-status.tsx` with status badges and duration display
- [x] T051 [US4] Create `apps/web/app/scrape-runs/page.tsx` listing mode, status, timing, counts, errors, debug paths
- [x] T052 [US4] Style `needs_manual_action` distinctly from generic `failed` in `apps/web/components/scrape-run-status.tsx`
- [x] T053 [US4] Add navigation links to scrape-runs, reviews, organizations in `apps/web/app/layout.tsx`

**Checkpoint**: Scrape history visible; failed runs show debug artifact references

---

## Phase 7: User Story 5 — Operator-Authenticated Scraping (Priority: P3)

**Goal**: Yandex operator login, saved session, operator-auth scrape mode

**Independent Test**: Login → session valid → operator-auth scrape stores reviews with correct mode

### Implementation for User Story 5

- [x] T054 [US5] Implement `yandex_auth.py` in `apps/api/app/scraper/yandex_auth.py` with login flow, storage_state save, headed/headless modes
- [x] T055 [US5] Implement scraper session endpoints in `apps/api/app/api/scraper_sessions.py` per `contracts/scraper-session-api.md`
- [x] T056 [US5] Integrate operator-auth path in `ScrapeService` reusing public parser after auth context in `apps/api/app/services/scrape_service.py`
- [x] T057 [US5] Ensure no password/cookie/storage contents in API responses or logs in `apps/api/app/api/scraper_sessions.py`
- [x] T058 [US5] Map captcha/2FA to `needs_manual_action` for session in `apps/api/app/scraper/yandex_auth.py`
- [x] T059 [US5] Add session status panel and login trigger to organizations board in `apps/web/app/organizations/page.tsx`
- [x] T060 [US5] Verify operator-auth scrape stores `scrape_mode=operator_auth` on reviews
- [x] T061 [US5] Verify expired session surfaces `needs_manual_action` per quickstart.md Milestone 4
- [x] T062 [US5] Register scraper_sessions router in `apps/api/app/main.py`

**Checkpoint**: Operator-auth vertical slice works; secrets never exposed

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: E2E tests, documentation, full verification

- [x] T063 Create `apps/web/tests/yandex-reviews-mvp.spec.ts` with E2E smoke: board load, create org (mock/seed), org detail reviews
- [x] T064 Update `README.md` with full verification commands from quickstart.md
- [x] T065 Run full API test suite: `cd apps/api && pytest -v`
- [x] T066 Run frontend lint and E2E: `cd apps/web && npm run lint && npm run test:e2e`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 — BLOCKS all user stories
- **US1 (Phase 3)**: Depends on Phase 2
- **US2 (Phase 4)**: Depends on Phase 2 + US1 (needs organizations)
- **US3 (Phase 5)**: Depends on Phase 2 + US2 (needs reviews data)
- **US4 (Phase 6)**: Depends on Phase 2 + US2 (needs scrape runs)
- **US5 (Phase 7)**: Depends on Phase 2 + US2 (extends scraper)
- **Polish (Phase 8)**: Depends on US1–US4 minimum; US5 for full feature

### User Story Dependencies

```text
Phase 2 (Foundation)
    ↓
US1 Organization Board
    ↓
US2 Public Scrape (MVP core)
    ↓
US3 Global Feed ──┐
US4 Scrape History ┼── can parallel after US2
US5 Operator Auth ─┘
    ↓
Polish
```

### Parallel Opportunities

- T002, T003, T004, T006, T007 within Phase 1
- T011 parallel with T009–T010 in Phase 2
- T023, T024 parallel in US1
- T039 parallel with T037–T038 in US2
- T050 parallel with T049 in US4
- US3 and US4 can run in parallel after US2 completes

---

## Parallel Example: User Story 1

```bash
# Parallel frontend types/client while backend service is built:
Task T023: apps/web/lib/types.ts
Task T024: apps/web/lib/api.ts

# Then sequential UI components:
Task T025 → T026 → T027 → T028
```

---

## Implementation Strategy

### MVP First (User Stories 1 + 2 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational
3. Complete Phase 3: US1 Organization Board
4. Complete Phase 4: US2 Public Review Collection
5. **STOP and VALIDATE** — public scrape vertical slice per quickstart Milestone 2–3

### Incremental Delivery

1. Setup + Foundational → DB and dedup ready
2. US1 → Organization management
3. US2 → Public scrape (core MVP)
4. US3 + US4 → Visibility and debugging
5. US5 → Operator auth
6. Polish → E2E and docs

---

## Task Summary

| Phase | Story | Tasks | Count |
|-------|-------|-------|-------|
| 1 | Setup | T001–T008 | 8 |
| 2 | Foundational | T009–T018 | 10 |
| 3 | US1 | T019–T028 | 10 |
| 4 | US2 | T029–T042 | 14 |
| 5 | US3 | T043–T048 | 6 |
| 6 | US4 | T049–T053 | 5 |
| 7 | US5 | T054–T062 | 9 |
| 8 | Polish | T063–T066 | 4 |
| **Total** | | | **66** |

**Suggested MVP scope**: Phases 1–4 (T001–T042) — Organization board + public scraping

**Independent test criteria**:
- US1: Add org URL → appears on board with pending status
- US2: Public scrape → reviews on detail; no duplicates on re-scrape
- US3: Global feed filters work across orgs
- US4: Failed scrape shows debug artifacts in history
- US5: Operator login → auth scrape with correct mode
