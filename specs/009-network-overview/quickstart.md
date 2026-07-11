# Quickstart / Validation: Network Overview Dashboard

Proves the overview works end-to-end. Assumes the Docker stack or local dev servers per repo README.

## Prerequisites

- API deps installed (`pip install -e ".[dev]"` in `apps/api`), Postgres up.
- Web deps installed (`npm install` in `apps/web`).
- At least a few organizations with reviews (run a scrape or seed fixtures).

## 1. Apply migration

```bash
cd apps/api
alembic upgrade head          # applies 0012_rating_snapshot
```

Expected: `rating_snapshot` table exists with unique `(organization_id, platform, captured_on)`.

## 2. Backend tests

```bash
cd apps/api
pytest tests/test_rating_snapshot.py tests/test_dashboard_overview.py -v
```

Expected: snapshot upsert is idempotent per day; overview aggregation reconciles to seeded reviews; empty network returns a zeroed 200 payload; org filter narrows results.

## 3. Snapshot capture

Trigger a scrape (single org) and confirm a `rating_snapshot` row for today is written for the scraped platform. Re-scrape same day → same row overwritten, not duplicated.

## 4. Endpoint smoke

```bash
curl -s "http://localhost:8000/api/dashboard/overview?period=30d&platform=all" | jq '.kpi_hero, .rating_distribution.total'
```

Expected: hero KPIs populated; `rating_distribution.total` equals count of reviews in the window. Deltas may be `null` on a fresh install (no history yet).

Filter checks:
- `?platform=yandex` → totals drop to Yandex-only.
- `?org_ids=<id>` → aggregates restricted to that organization.

## 5. Frontend

```bash
cd apps/web
npm run dev
```

Open `http://localhost:3000/` (dashboard home). Expected:
- Greeting header + 3 hero KPIs + 5 mini KPIs render.
- Rating distribution bars, sentiment donut, platform donut render and sum to network totals.
- 3 platform cards; Google per-review metrics show "нет данных".
- Attention feed lists unanswered>24h / escalated items with working links.
- Worst-locations and trending-aspects tables populated.
- Changing period / platform / organization filters updates the URL and recomputes all blocks (< 2s).

## 6. Gate

```bash
cd apps/api && pytest -v
cd apps/web && npm run lint && npm run test:e2e
```

Expected: all green, including `tests-e2e/dashboard.spec.ts`.
