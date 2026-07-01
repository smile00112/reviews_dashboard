# Yandex Reviews MVP

Internal dashboard for collecting and displaying Yandex Maps organization reviews.

## Stack

- **API**: FastAPI, SQLAlchemy, Alembic, Playwright, BeautifulSoup, requests (Python)
- **Web**: Next.js, TypeScript, TailwindCSS
- **DB**: PostgreSQL 16

## Quick Start

```bash
cp .env.example .env
docker compose up --build
```

- Dashboard: http://localhost:3000
- API: http://localhost:8000
- Health: http://localhost:8000/health

## Local Development

### API

```bash
cd apps/api
pip install -e ".[dev]"
playwright install chromium
alembic upgrade head
uvicorn app.main:app --reload
```

### Web

```bash
cd apps/web
npm install
npm run dev
```

## Verification

```bash
cd apps/api && pytest -v
cd ../web && npm run lint && npm run test:e2e
```

See `specs/001-yandex-reviews-mvp/quickstart.md` for milestone validation steps.

## Environment Variables

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | PostgreSQL connection string |
| `YANDEX_OPERATOR_LOGIN` | Yandex account for operator_auth mode |
| `YANDEX_OPERATOR_PASSWORD` | Yandex password |
| `YANDEX_STORAGE_STATE_PATH` | Playwright session file path |
| `SCRAPER_DEBUG_DIR` | Failed scrape debug artifacts |
| `NEXT_PUBLIC_API_URL` | API URL for web frontend |

## Features

- Organization board with manual scrape triggers
- Public and operator-auth Playwright scraping
- Browserless HTTP scraping (`public_http` mode) on a dedicated `/http-scraper` page —
  requests + pagination, bot-protection surfaces as `needs_manual_action` (no bypass)
- Review deduplication by content hash
- Global reviews feed with filters
- Scrape run history with debug artifact paths
- Rule-based review analytics: sentiment, problem categorization, rating↔sentiment mismatch
  (deterministic, local, no LLM) — `POST /api/organizations/{id}/analyze` (backfill),
  `GET /api/organizations/{id}/analytics` (per-org summary)

## Spec Kit Artifacts

- Specs: `specs/001-yandex-reviews-mvp/`, `specs/002-review-analytics/`, `specs/003-http-scraper/` (each has spec.md / plan.md / tasks.md)
- Constitution: `.specify/memory/constitution.md` (v1.1.0)
