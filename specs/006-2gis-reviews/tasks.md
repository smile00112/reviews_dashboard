# Tasks: 2GIS Review Collection (twogis_api mode)

**Feature**: `006-2gis-reviews` | **Plan**: [plan.md](./plan.md)

Ordered; `[P]` = parallelizable with the previous task.

## Phase 1 — Enum & settings

- [ ] **T001** Add `twogis_api = "twogis_api"` to `ScrapeMode` in `app/models/enums.py`.
- [ ] **T002** [P] Add 2GIS settings to `app/core/config.py`: `twogis_catalog_key`
      (default `"rubnkm7490"`), `twogis_review_key` (default `"6e7e1929-4ea9-4a5d-8c05-d601860389bd"`),
      `twogis_review_limit` (150), `twogis_page_size` (50), `twogis_request_delay_seconds` (0.3).
- [ ] **T003** [P] Update `.env.example` with the 2GIS keys (documented as public defaults).

## Phase 2 — Scraper

- [ ] **T004** Create `app/scraper/twogis_api.py` with `TwogisApiScraper`:
      `_resolve_firm_id`, `_catalog_lookup`, `_fetch_reviews`, `_map_review`, `_get_json`
      (direct + ScrapeOps fallback), `_redact`. Returns standard `ScrapeResult`.
- [ ] **T005** Handle outcomes: no firm id → `error_code="twogis_no_firm_id"`;
      blocked catalog key (403 `apiKeyIsBlocked`) → `needs_manual_action`;
      bot wall on proxy HTML → `needs_manual_action`; never raise out of `scrape`.

## Phase 3 — Persistence & wiring

- [ ] **T006** `app/services/review_service.py`: derive `source`/`platform` from `scrape_mode`
      (`twogis_api` → `source="2gis"`, `platform=ReviewPlatform.gis2`); leave hash inputs untouched.
- [ ] **T007** `app/services/scrape_service.py`: construct `TwogisApiScraper`; branch
      `mode == ScrapeMode.twogis_api` → `self.twogis_scraper.scrape(url)`.
- [ ] **T008** Alembic `0006_twogis_api_mode.py`: `ALTER TYPE scrape_mode_enum ADD VALUE
      IF NOT EXISTS 'twogis_api'` (autocommit, Postgres-only; mirror 0005). down_revision `0005_scrapeops_mode`.

## Phase 4 — Tests (Principle III critical-path)

- [ ] **T009** `tests/test_twogis_api.py`: `_map_review` produces correct `ParsedReview`;
      `review_date_text` = `date_created`; `official_answer` → `response_text`.
- [ ] **T010** [P] Dedup parity: two scrapes of the same fixture reviews insert then 0-insert
      (mock `_get_json`); assert `content_hash` stable and `scrape_mode=twogis_api`.
- [ ] **T011** [P] Blocked catalog key → `needs_manual_action`, no exception.
- [ ] **T012** [P] `_resolve_firm_id`: full `/firm/{id}` URL → id with no network;
      short link → uses ScrapeOps path (mocked).

## Phase 5 — Verification

- [ ] **T013** `pytest -v` green (existing + new); Yandex modes unaffected.
- [ ] **T014** Manual smoke against a real 2GIS URL with `SCRAPEOPS_API_KEY` set
      (documented; not a CI gate).
