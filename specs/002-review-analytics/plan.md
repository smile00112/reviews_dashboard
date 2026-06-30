# Implementation Plan: Review Analytics & Structured Parsing

**Branch**: `002-review-analytics` | **Date**: 2026-06-30 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/002-review-analytics/spec.md`

## Summary

Add deterministic, local rule-based analytics over collected reviews (sentiment, problem
categorization, rating↔sentiment mismatch) and harden the scraper's HTML parsing
(BeautifulSoup, date normalization, guest-review filtering). Ported from the sibling
`BrandTrackerAI_Parser` project, keeping only the deterministic local pieces. No LLM, no
new services, no schedulers, no other map providers. Analytics are additive to the
existing `Review` data and never alter the dedup `content_hash`.

## Technical Context

**Language/Version**: Python 3.12 (API); no web-stack change required for P1/P2 backend, optional read-only UI surfacing later.

**Primary Dependencies**: existing FastAPI, SQLAlchemy 2, Alembic, Playwright; **adds** `beautifulsoup4` (structured parsing). Analytics use stdlib only (`re`, `collections.Counter`) — no pandas, no ML libs.

**Storage**: PostgreSQL 16. Additive columns on `reviews` for sentiment fields + a JSONB `problems` column. One Alembic migration. No new tables (YAGNI; one-to-one with review).

**Testing**: pytest. New tests: sentiment classification, problem extraction, date normalization, guest-review filter, analytics summary aggregation, dedup-hash-unchanged regression.

**Target Platform**: same Docker Compose stack.

**Project Type**: Web application monorepo (`apps/api` + `apps/web`); this feature is API-centric.

**Performance Goals**: per-review analysis is O(text length) dictionary scan; org summary computed on read over an org's reviews (tens of orgs, low thousands of reviews) — well within request budget.

**Constraints**: Deterministic & local only (Principle VI); no external inference; safe degradation on bad input; raw review fields and `content_hash` immutable.

**Scale/Scope**: same internal tool scale, ~5–50 orgs, hundreds to low thousands of reviews.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. MVP Scope Discipline | ✅ Pass | Analytics added to scope by v1.1.0 amendment; 2GIS/scheduler/CSV NOT ported |
| II. Read-Only Review Collection | ✅ Pass | Analytics are derived, display-only; no publish/edit |
| III. Critical-Path Testing | ✅ Pass | Tests for sentiment, problems, date normalize, summary, hash-unchanged |
| IV. Scraper Reliability & Debuggability | ✅ Pass | bs4 parser keeps scrape-run records + debug artifacts; date parse degrades safely |
| V. Simplicity (YAGNI) | ✅ Pass | stdlib analytics, JSONB instead of join table, no new services |
| VI. Deterministic Local Analytics | ✅ Pass | Rule-based dictionaries/regex, local, safe-degrading, hash-preserving |

**Post-design re-check**: All gates pass. No Complexity Tracking entries required.

## Project Structure

### Documentation (this feature)

```text
specs/002-review-analytics/
├── plan.md              # This file
├── data-model.md        # Phase 1 output
├── contracts/
│   └── analytics-api.md
└── tasks.md             # Phase 2 output (/speckit-tasks)
```

### Source Code (additions to existing layout)

```text
apps/api/app/
├── analysis/                    # NEW — deterministic local analytics
│   ├── __init__.py
│   ├── sentiment.py             # SentimentAnalyzer (dicts + intensifiers)
│   ├── problems.py              # ProblemExtractor (8-category taxonomy)
│   └── analyzer.py              # ReviewAnalyzer: combine + mismatch + summary
├── scraper/
│   ├── parser.py                # REWRITE: BeautifulSoup-based extraction
│   └── normalize.py             # ADD normalize_review_date()
├── services/
│   ├── review_service.py        # call analysis on upsert (after hash)
│   └── analysis_service.py      # NEW: backfill + per-org summary
├── models/review.py             # ADD sentiment*, problems (JSONB), mismatch cols
├── schemas/review.py            # expose analysis fields
├── schemas/analytics.py         # NEW: summary response model
├── api/reviews.py               # expose analysis; analyze trigger
└── api/organizations.py         # GET /{id}/analytics summary
alembic/versions/0002_*.py       # NEW migration (additive columns)
```

**Structure Decision**: Analytics live in a new `app/analysis/` package (pure, no DB), called by a thin `AnalysisService` (takes a `Session`, like other services) — same layering discipline as existing services. Parser hardening stays inside `app/scraper/`.

## Key Design Decisions

1. **Storage shape**: additive columns on `reviews` (`sentiment` text, `sentiment_score` float, `sentiment_confidence` float, `rating_sentiment_mismatch` bool, `analyzed_at` timestamp) plus `problems` JSONB. Rejected separate `review_analysis` + `problems` tables as premature (one-to-one, low volume) — recorded under YAGNI.
2. **Hash safety**: analysis computed strictly after `build_review_hash`; analysis fields are NOT hash inputs. A regression test asserts hashes are unchanged before/after analysis.
3. **Pure analytics package**: `sentiment.py`/`problems.py`/`analyzer.py` are dependency-free (stdlib), making them trivially unit-testable and reusable; pandas from the source project is dropped.
4. **Summary on read**: org summary is computed by `AnalysisService` from stored per-review fields — no materialized aggregate table.
5. **Parser swap is isolated**: `parse_reviews_from_html` keeps its signature `(html) -> (ParsedOrganization, list[ParsedReview])`; only internals change to bs4. `ParsedReview` gains an optional normalized `review_date`.
6. **Backfill path**: `POST /api/organizations/{id}/analyze` (and/or analyze-on-upsert) lets analysis run over already-stored reviews; idempotent.

## Complexity Tracking

> No constitution violations requiring justification.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| — | — | — |

## Delivery Milestones

1. **Analytics core** — `app/analysis/` package + unit tests (sentiment, problems, mismatch). Pure, no DB. (US1 logic)
2. **Persistence & API** — migration, model/schema fields, `AnalysisService`, analyze-on-upsert + backfill endpoint, reviews API exposes analysis. (US1 end-to-end)
3. **Org summary** — `GET /api/organizations/{id}/analytics` + aggregation tests. (US2)
4. **Parser hardening** — bs4 rewrite, date normalization, guest filter + fixture tests. (US3)
