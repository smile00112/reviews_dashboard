# Quickstart: Yandex Reviews MVP

**Date**: 2026-06-14

Validation guide for proving each delivery milestone works end-to-end. See
[data-model.md](./data-model.md) and [contracts/](./contracts/) for details.

## Prerequisites

- Docker and Docker Compose
- Node.js 20+
- Python 3.12+ (for local API dev without Docker)
- Copy `.env.example` to `.env` and set variables:

```text
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/yandex_reviews
YANDEX_OPERATOR_LOGIN=
YANDEX_OPERATOR_PASSWORD=
YANDEX_STORAGE_STATE_PATH=.local/yandex-storage-state.json
SCRAPER_DEBUG_DIR=.local/scraper-debug
```

## Milestone 1: Data Backbone

### Setup

```bash
docker compose up --build -d postgres
cd apps/api
pip install -e ".[dev]"
alembic upgrade head
uvicorn app.main:app --reload
```

### Verify

```bash
curl http://localhost:8000/health
# Expected: {"status":"ok"}

curl -X POST http://localhost:8000/api/organizations \
  -H "Content-Type: application/json" \
  -d '{"yandex_url":"https://yandex.ru/maps/org/test/123/","preferred_scrape_mode":"public"}'

curl http://localhost:8000/api/organizations

cd apps/api
pytest tests/test_review_deduplication.py tests/test_organizations_api.py -v
```

**Pass criteria**: Health OK; organization CRUD works; deduplication test passes.

## Milestone 2: Public Scraper Vertical Slice

### Verify

```bash
# Replace {org_id} with created organization UUID
curl -X POST http://localhost:8000/api/organizations/{org_id}/scrape \
  -H "Content-Type: application/json" \
  -d '{"mode":"public"}'

curl http://localhost:8000/api/scrape-runs

curl http://localhost:8000/api/organizations/{org_id}/reviews

# Run scrape again — review count should not duplicate
curl -X POST http://localhost:8000/api/organizations/{org_id}/scrape \
  -H "Content-Type: application/json" \
  -d '{"mode":"public"}'
```

**Pass criteria**: Scrape run reaches `success`; reviews appear; second scrape does not
duplicate; failed scrape (bad URL) has error + debug artifact paths.

## Milestone 3: Dashboard

### Setup

```bash
cd apps/web
npm install
npm run dev
# Open http://localhost:3000
```

### Manual QA

1. Add organization by Yandex Maps URL on organization board
2. Click **Обновить** — confirm row status updates after scrape
3. Open organization detail — confirm reviews visible
4. Open global reviews page — confirm filters work
5. Open scrape runs page — confirm history and error display

```bash
cd apps/web
npm run lint
npm run test:e2e
```

**Pass criteria**: UI flows work; E2E smoke tests pass; lint clean.

## Milestone 4: Operator Auth Mode

### Verify

1. Set `YANDEX_OPERATOR_LOGIN` and `YANDEX_OPERATOR_PASSWORD` in `.env`
2. `POST /api/scraper/yandex/login` — session status becomes `valid`
3. Set organization preferred mode to `operator_auth`
4. Trigger scrape — reviews stored with `scrape_mode: operator_auth`
5. Expire/delete storage state — status becomes `needs_manual_action`

**Pass criteria**: Auth scrape collects reviews; secrets never in API responses;
captcha/2FA surfaces as `needs_manual_action`.

## Full Stack (Docker Compose)

```bash
docker compose up --build
cd apps/api && pytest -v
cd ../web && npm run lint && npm run test:e2e
```

## Manual QA Checklist (from spec)

- [ ] Add organization by Yandex Maps URL
- [ ] Run public scrape; confirm row updates
- [ ] Open organization page; confirm reviews visible
- [ ] Re-run public scrape; confirm no duplicates
- [ ] Configure operator credentials; run login; session `valid`
- [ ] Run operator-auth scrape; reviews have operator_auth mode
- [ ] Force bad URL — failed run with readable error
- [ ] Force expired session — `needs_manual_action`
