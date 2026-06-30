# Tasks: Review Analytics & Structured Parsing

**Input**: Design documents from `/specs/002-review-analytics/`

**Prerequisites**: plan.md, spec.md, data-model.md, contracts/analytics-api.md

**Organization**: Tasks grouped by phase / user story for independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: User story label (US1–US3)

## Phase 1: Setup

- [x] T001 Add `beautifulsoup4` to `apps/api/pyproject.toml` dependencies
- [x] T002 Create `apps/api/app/analysis/__init__.py` package marker

**Checkpoint**: package importable, dependency declared

---

## Phase 2: User Story 1 — Per-review sentiment & problems (Priority: P1) 🎯 MVP

**Goal**: Each review classified (sentiment) and tagged with problem categories; persisted and exposed via API.

**Independent Test**: Known texts → expected sentiment/problems; analyzed review exposes fields via reviews API.

### Analytics core (pure, stdlib only)

- [x] T003 [P] [US1] Implement `SentimentAnalyzer` in `apps/api/app/analysis/sentiment.py` (pos/neg dictionaries, intensifiers, bounded score, safe-degrade on empty/None)
- [x] T004 [P] [US1] Implement `ProblemExtractor` in `apps/api/app/analysis/problems.py` (8-category taxonomy, keywords, severity, context)
- [x] T005 [US1] Implement `ReviewAnalyzer` in `apps/api/app/analysis/analyzer.py` combining sentiment + problems + rating↔sentiment mismatch (no pandas)
- [x] T006 [P] [US1] Create `apps/api/tests/test_sentiment_analyzer.py` (positive/negative/neutral, negation, empty input no-raise)
- [x] T007 [P] [US1] Create `apps/api/tests/test_problem_extractor.py` (category detection, multi-category, severity, empty input)

### Persistence & wiring

- [x] T008 [US1] Add analysis columns to `apps/api/app/models/review.py` (`sentiment`, `sentiment_score`, `sentiment_confidence`, `rating_sentiment_mismatch`, `problems` JSONB, `analyzed_at`)
- [x] T009 [US1] Create Alembic migration `apps/api/alembic/versions/0002_review_analysis.py` (additive nullable columns)
- [x] T010 [US1] Expose analysis fields in `apps/api/app/schemas/review.py`
- [x] T011 [US1] Create `apps/api/app/services/analysis_service.py` with `analyze_review`, `analyze_organization` (backfill, idempotent), `summary`
- [x] T012 [US1] Call analysis after hashing in `ReviewService.upsert_reviews` (`apps/api/app/services/review_service.py`); analysis MUST NOT feed `content_hash`
- [x] T013 [US1] Add `POST /api/organizations/{id}/analyze` backfill endpoint in `apps/api/app/api/organizations.py`
- [x] T014 [US1] Create `apps/api/tests/test_review_analysis_hash_unchanged.py` proving `content_hash` is identical before/after analysis (dedup contract regression)

**Checkpoint**: reviews carry sentiment/problems; backfill endpoint works; hash unchanged

---

## Phase 3: User Story 2 — Per-organization analytics summary (Priority: P2)

**Goal**: Aggregate summary endpoint (sentiment distribution, top problems, mismatch count).

**Independent Test**: Seed analyzed reviews → summary endpoint returns hand-computed aggregates.

- [x] T015 [US2] Create `apps/api/app/schemas/analytics.py` `OrganizationAnalyticsSummary` per contract
- [x] T016 [US2] Implement `AnalysisService.summary(org_id)` aggregation (distribution, percent, top problems, mismatch count, empty-org zeroed)
- [x] T017 [US2] Add `GET /api/organizations/{id}/analytics` in `apps/api/app/api/organizations.py` (404 unknown org)
- [x] T018 [US2] Create `apps/api/tests/test_analytics_summary.py` (distribution counts/percent, top-problem ranking, mismatch count, empty org → 200 zeroed)

**Checkpoint**: analytics summary returns correct aggregates

---

## Phase 4: User Story 3 — Structured parsing, date normalization, guest filter (Priority: P3)

**Goal**: bs4 parser, `review_date` populated from normalized date text, owner responses excluded from guest reviews.

**Independent Test**: HTML fixtures → extracted author/rating/date + populated `review_date`; owner responses not emitted as guest reviews.

- [x] T019 [US3] Add `normalize_review_date(text, *, today)` to `apps/api/app/scraper/normalize.py` (relative forms, RU/EN months, `DD.MM.YYYY`; unparseable → None, no raise)
- [x] T020 [P] [US3] Create `apps/api/tests/test_review_date_normalize.py` (вчера/сегодня, N дней назад, "2 мая 2024", "2 мая", DD.MM.YYYY, garbage → None)
- [x] T021 [US3] Rewrite `parse_reviews_from_html` in `apps/api/app/scraper/parser.py` using BeautifulSoup; populate `ParsedReview.review_date` via `normalize_review_date`; keep signature
- [x] T022 [US3] Add guest-review filter (exclude owner/business responses) in `apps/api/app/scraper/parser.py`; preserve `response_text` behavior
- [x] T023 [US3] Add `review_date` field to `ParsedReview` in `apps/api/app/scraper/types.py` and persist it in `ReviewService.upsert_reviews`
- [x] T024 [P] [US3] Capture Yandex review-page HTML fixture(s) under `apps/api/tests/fixtures/` and create `apps/api/tests/test_yandex_parser.py` (author/rating/date extraction, owner-response excluded)

**Checkpoint**: parser bs4-based, dates normalized, responses filtered

---

## Phase 5: Polish & Validation

- [x] T025 Update `CLAUDE.md` and `README.md` with the analytics module, endpoints, and `beautifulsoup4` dependency
- [x] T026 Run full API test suite: `cd apps/api && pytest -v` — all pass
- [ ] T027 Run `alembic upgrade head` and verify reviews API returns analysis fields end-to-end — **PENDING live Postgres**. Migration 0002 validated offline (`alembic upgrade --sql` emits correct JSONB DDL); analysis fields verified end-to-end against the SQLite test DB. Run on a live DB before deploy.

**Checkpoint**: all tests green; migration validated offline (live apply pending DB); analytics live in tests

---

## Dependencies

- Phase 1 → all.
- US1 (Phase 2) is the MVP slice; US2 depends on US1 persistence; US3 is independent of US1/US2 (can be sequenced last or in parallel by a separate worker).
- Within US1: core analytics (T003–T007) before persistence/wiring (T008–T014).
