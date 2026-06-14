# Yandex Reviews MVP

Internal dashboard for collecting and displaying Yandex Maps organization reviews.

## Stack

- **API**: FastAPI, SQLAlchemy, Alembic, Playwright (Python)
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
- Review deduplication by content hash
- Global reviews feed with filters
- Scrape run history with debug artifact paths

## Spec Kit Artifacts

- Spec: `specs/001-yandex-reviews-mvp/spec.md`
- Plan: `specs/001-yandex-reviews-mvp/plan.md`
- Tasks: `specs/001-yandex-reviews-mvp/tasks.md`
