# Implementation Plan: Yandex Reviews MVP

**Branch**: `001-yandex-reviews-mvp` | **Date**: 2026-06-14 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/001-yandex-reviews-mvp/spec.md`

**Reference**: Detailed implementation notes in `docs/plans/2026-06-14-yandex-reviews-mvp.md`

## Summary

Build a minimal internal dashboard that collects Yandex Maps organization reviews through
Playwright and displays organizations, reviews, scrape status, and scrape errors. The MVP
is read-only (no replies, no app auth). Architecture: Next.js dashboard, FastAPI backend,
PostgreSQL storage, Playwright scraper with public and operator-auth modes. Scrapes run as
FastAPI background tasks; failed runs save debug artifacts.

## Technical Context

**Language/Version**: Python 3.12 (API), TypeScript / Node 20 (web)

**Primary Dependencies**: FastAPI, SQLAlchemy 2, Alembic, Playwright (Python), Next.js 14+,
TailwindCSS, shadcn/ui, psycopg3

**Storage**: PostgreSQL 16; local filesystem for Playwright storage state and scraper debug
artifacts (`.local/`)

**Testing**: pytest (API unit/integration), Playwright E2E (web smoke)

**Target Platform**: Docker Compose on Linux/macOS/Windows dev machines; headless Chromium
for server scrapes, headed optional for local auth debugging

**Project Type**: Web application (monorepo: `apps/api` + `apps/web`)

**Performance Goals**: Single-organization public scrape completes within operational limits
(30s page load, up to 40 review-panel scrolls); dashboard responsive for tens of orgs

**Constraints**: No Celery/Redis queue; no application auth; no captcha bypass; operator
credentials via env only; scrape concurrency limited to background-task model for MVP

**Scale/Scope**: Internal tool, ~5–50 organizations, hundreds to low thousands of reviews

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. MVP Scope Discipline | ✅ Pass | Plan excludes auth, replies, LLM, Celery, other map providers |
| II. Read-Only Review Collection | ✅ Pass | Scraper stores visible responses only; no publish API |
| III. Critical-Path Testing | ✅ Pass | Tests planned for dedup, normalize, org/scrape APIs |
| IV. Scraper Reliability & Debuggability | ✅ Pass | Scrape runs + debug artifacts on failure |
| V. Simplicity (YAGNI) | ✅ Pass | Background tasks, monorepo, Docker Compose |

**Post-design re-check**: All gates pass. No Complexity Tracking entries required.

## Project Structure

### Documentation (this feature)

```text
specs/001-yandex-reviews-mvp/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   ├── organizations-api.md
│   ├── reviews-api.md
│   ├── scrape-api.md
│   └── scraper-session-api.md
├── checklists/
│   └── requirements.md
└── tasks.md             # Phase 2 output (/speckit-tasks)
```

### Source Code (repository root)

```text
.
├── apps/
│   ├── api/
│   │   ├── app/
│   │   │   ├── api/           # FastAPI routers
│   │   │   ├── core/          # config, database
│   │   │   ├── models/        # SQLAlchemy models
│   │   │   ├── schemas/       # Pydantic schemas
│   │   │   ├── scraper/       # Playwright + parser + normalize
│   │   │   ├── services/      # business logic
│   │   │   └── main.py
│   │   ├── alembic/
│   │   ├── tests/
│   │   └── pyproject.toml
│   └── web/
│       ├── app/               # Next.js App Router pages
│       ├── components/
│       ├── lib/               # api client, types
│       └── tests/             # Playwright E2E
├── docker-compose.yml
├── .env.example
└── README.md
```

**Structure Decision**: Monorepo web application per reference plan. API owns scraping;
web is read/write UI calling REST API. Shared nothing except HTTP contract.

## Complexity Tracking

> No constitution violations requiring justification.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| — | — | — |

## Delivery Milestones

1. **Data Backbone** — API scaffold, DB schema, organization CRUD, reviews API, scrape run records
2. **Public Scraper Vertical Slice** — Public Playwright scraper, one-org scrape, dedup, debug artifacts
3. **Dashboard** — Organization board, detail, global reviews, scrape history UI
4. **Operator Auth Mode** — Login flow, saved session, authenticated scrape

See [quickstart.md](./quickstart.md) for verification steps per milestone.
