# Implementation Plan: HTTP Review Scraper (public_http mode)

**Branch**: `003-http-scraper` | **Date**: 2026-06-30 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/003-http-scraper/spec.md`

## Summary

Port the browserless `MultiPageYandexParser` (requests + BeautifulSoup, `?page=N`
pagination) from `BrandTrackerAI_Parser` into a new `YandexHttpScraper` behind a new
`public_http` scrape mode. Wire it into the existing `ScrapeService` so it reuses the
background-task flow, `ScrapeRun` records, dedup, and feature-002 analytics. Add a
dedicated web page to drive it. Playwright `public`/`operator_auth` modes are untouched.

## Technical Context

**Language/Version**: Python 3.12 (API), TypeScript / Node 20 (web).

**Primary Dependencies**: existing FastAPI, SQLAlchemy, Alembic; **adds** `requests` (HTTP).
Reuses feature-002 `beautifulsoup4` + `parse_reviews_from_html` + `normalize_review_date`.

**Storage**: PostgreSQL 16. **No schema tables added**; one enum value `public_http` added to
the `scrape_mode_enum` / `review_scrape_mode_enum` Postgres types (Alembic `ALTER TYPE ... ADD VALUE`).

**Testing**: pytest. New: HTTP scraper unit tests over fixture HTML (extraction +
bot-detection → needs_manual_action) and `ScrapeService` routing to `public_http`.

**Target Platform**: same Docker Compose stack; HTTP scraper needs no browser.

**Project Type**: Web application monorepo (`apps/api` + `apps/web`).

**Performance Goals**: bounded by `max_pages` (default 5) × inter-page delay; seconds per org.

**Constraints**: Read-only; no captcha bypass (challenge → `needs_manual_action`); additive
mode only; polite request delay + realistic headers.

**Scale/Scope**: same internal tool scale.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. MVP Scope Discipline | ✅ Pass | "Public scraping" already in scope; mode additive; 2GIS/scheduler/CSV NOT ported |
| II. Read-Only Review Collection | ✅ Pass | Fetch + parse only; no publish/edit |
| III. Critical-Path Testing | ✅ Pass | Tests for extraction, bot-detection, mode routing; dedup/analytics reused & already tested |
| IV. Scraper Reliability & Debuggability | ✅ Pass | ScrapeRun per attempt; challenge → needs_manual_action + HTML debug artifact; no silent retry/bypass |
| V. Simplicity (YAGNI) | ✅ Pass | Reuses parser, persistence, background tasks; no new tables/services |
| VI. Deterministic Local Analytics | ✅ Pass | Analytics path unchanged; runs on stored reviews as before |

**Post-design re-check**: All gates pass. No Complexity Tracking entries required. No constitution amendment needed.

## Project Structure

### Documentation (this feature)

```text
specs/003-http-scraper/
├── plan.md
├── data-model.md
├── contracts/
│   └── http-scrape.md
└── tasks.md
```

### Source Code (additions to existing layout)

```text
apps/api/app/
├── scraper/
│   ├── yandex_http.py          # NEW — YandexHttpScraper (requests + pagination)
│   └── debug_artifacts.py      # ADD save_html_debug(html, prefix) (browserless artifact)
├── services/scrape_service.py  # route public_http -> YandexHttpScraper
├── models/enums.py             # add ScrapeMode.public_http
└── core/config.py              # http scraper settings (limit, max_pages, delay, headers)
alembic/versions/0003_*.py      # ALTER TYPE ... ADD VALUE 'public_http' (both enum types)
apps/web/
├── app/http-scraper/page.tsx   # NEW dedicated page
├── app/layout.tsx              # nav link
├── components/                 # reuse reviews-table / scrape-run-status
└── lib/types.ts                # add 'public_http' to ScrapeMode
```

**Structure Decision**: `YandexHttpScraper` mirrors the `YandexPublicScraper` interface
(`scrape(url) -> ScrapeResult`) so `ScrapeService` only gains one routing branch. Review
extraction is delegated to the existing `parse_reviews_from_html` (feature 002) — the HTTP
scraper only owns fetching, pagination, and bot-detection.

## Key Design Decisions

1. **Reuse the parser**: each fetched page's HTML goes through `parse_reviews_from_html`; the scraper aggregates reviews across pages and takes organization metadata from the first page. No duplicate extraction logic.
2. **Interface parity**: `YandexHttpScraper.scrape(url)` returns `ScrapeResult`, identical to `YandexPublicScraper`, so `ScrapeService._scrape_organization` adds a single `public_http` branch and everything downstream (persist, dedup, analytics, status) is unchanged.
3. **Enum extension**: add `public_http` via `ALTER TYPE ... ADD VALUE`. Python `ScrapeMode` gains the member; existing rows/modes unaffected.
4. **Bot-detection**: markers ("Обнаружена защита от ботов" + reused captcha markers) → `ScrapeResult.needs_manual_action` with an HTML debug artifact saved by a new browserless `save_html_debug` helper. No bypass.
5. **No new endpoint / no new tables**: the existing `POST /api/organizations/{id}/scrape` already takes `mode`; passing `public_http` is sufficient. Web page calls it and polls `ScrapeRun`.
6. **Settings-driven limits**: `limit`, `max_pages`, request delay, and headers live in `core/config.py` with defaults (150 / 5).

## Complexity Tracking

> No constitution violations requiring justification.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| — | — | — |

## Delivery Milestones

1. **Scraper core** — `YandexHttpScraper` + `save_html_debug` + unit tests (extraction, pagination stop, bot-detection). (US1 logic)
2. **Mode wiring** — enum value, migration 0003, config settings, `ScrapeService` routing + routing test. (US1 end-to-end)
3. **Web page** — dedicated `/http-scraper` page, nav link, types/mode-select update. (US2)
