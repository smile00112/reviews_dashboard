# Tasks: HTTP Review Scraper (public_http mode)

**Input**: Design documents from `/specs/003-http-scraper/`

**Prerequisites**: plan.md, spec.md, data-model.md, contracts/http-scrape.md

**Organization**: Tasks grouped by phase / user story for independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: User story label (US1–US2)

## Phase 1: Setup

- [x] T001 Add `requests` to `apps/api/pyproject.toml` dependencies
- [x] T002 Add HTTP-scraper settings to `apps/api/app/core/config.py` (`http_scrape_limit=150`, `http_scrape_max_pages=5`, `http_scrape_delay_seconds=2.0`, `http_scrape_user_agent`)

**Checkpoint**: dependency + settings available

---

## Phase 2: User Story 1 — Browserless HTTP scrape end-to-end (Priority: P1) 🎯 MVP

**Goal**: A `public_http` scrape fetches, parses, dedups, analyzes, and stores reviews with a ScrapeRun.

**Independent Test**: Run `public_http` against fixture HTML → reviews stored `scrape_mode=public_http`, ScrapeRun success with counts; bot-marker → needs_manual_action.

### Scraper core

- [x] T003 [US1] Add `save_html_debug(html, prefix)` to `apps/api/app/scraper/debug_artifacts.py` (browserless HTML artifact)
- [x] T004 [US1] Implement `YandexHttpScraper.scrape(url)` in `apps/api/app/scraper/yandex_http.py` (requests.Session + headers, `?page=N` pagination, limit/max_pages/delay from settings, aggregate via `parse_reviews_from_html`, org from first page, bot-detection → `needs_manual_action` + `save_html_debug`, network errors skip page, return `ScrapeResult`)
- [x] T005 [P] [US1] Create `apps/api/tests/fixtures/yandex_http_page.html` (page with `business-review-view` blocks) and `apps/api/tests/fixtures/yandex_http_botwall.html` (bot-protection marker)
- [x] T006 [P] [US1] Create `apps/api/tests/test_yandex_http_scraper.py` (extraction from fixture via monkeypatched fetch, pagination stop on empty page, bot-marker → needs_manual_action with debug_html)

### Mode wiring

- [x] T007 [US1] Add `public_http` to `ScrapeMode` in `apps/api/app/models/enums.py`
- [x] T008 [US1] Create Alembic migration `apps/api/alembic/versions/0003_public_http_mode.py` (`ALTER TYPE scrape_mode_enum ADD VALUE IF NOT EXISTS 'public_http'` inside an autocommit block). NOTE during impl: migration 0001 used a single shared `scrape_mode_enum` for all three mode columns, so only one ALTER TYPE is needed (not a separate `review_scrape_mode_enum`).
- [x] T009 [US1] Route `public_http` to `YandexHttpScraper` in `ScrapeService._scrape_organization` (`apps/api/app/services/scrape_service.py`); inject `http_scraper` in `__init__`
- [x] T010 [US1] Create `apps/api/tests/test_scrape_mode_routing.py` (mock scrapers: `public_http` calls `YandexHttpScraper`, persists with `scrape_mode=public_http`, ScrapeRun success; second run dedups to 0 inserted)

**Checkpoint**: public_http scrape works end-to-end against fixtures; existing modes unchanged

---

## Phase 3: User Story 2 — Dedicated web page (Priority: P2)

**Goal**: Separate page to run HTTP scrapes per org and view results.

**Independent Test**: Load page, trigger scrape for an org, see run status reach terminal, see org reviews.

- [x] T011 [US2] Add `'public_http'` to `ScrapeMode` type in `apps/web/lib/types.ts` and option in `apps/web/components/mode-select.tsx`
- [x] T012 [US2] Create `apps/web/app/http-scraper/page.tsx`: list organizations, per-org "Scrape (HTTP)" button → `POST /scrape` with `mode=public_http`, poll `GET /scrape-runs/{id}`, render run status + selected org reviews (reuse `scrape-run-status` + `reviews-table`)
- [x] T013 [US2] Add nav link to the HTTP Scraper page in `apps/web/app/layout.tsx`

**Checkpoint**: dedicated page drives a full HTTP scrape and shows reviews

---

## Phase 4: Polish & Validation

- [x] T014 Update `CLAUDE.md` (new mode + scraper) and `README.md` (`requests` dep, public_http mode, page)
- [x] T015 Run full API test suite: `cd apps/api && pytest -v` — all pass
- [x] T016 Verify migration 0003 and apply on live DB — **DONE**. `alembic upgrade head` applied on live Postgres `yandex_reviews` (head=`0003_public_http_mode`); `scrape_mode_enum` now has `['public','operator_auth','public_http']`. End-to-end verified: upsert with `scrape_mode=public_http` persists, analysis fields populate (sentiment/mismatch/problems), `ReviewResponse` serializes them, org analytics summary aggregates. Test rows cleaned up.

---

## Dependencies

- Phase 1 → all.
- US1 scraper core (T003–T006) before mode wiring (T007–T010).
- US2 (web) depends on the enum value (T007) and the scrape path (T009) existing.
