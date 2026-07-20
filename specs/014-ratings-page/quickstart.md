# Quickstart: Ratings Page

Validation guide for feature 014. See [contracts/dashboard-ratings.md](./contracts/dashboard-ratings.md) for the payload shape and [data-model.md](./data-model.md) for field semantics.

## Prerequisites

- Postgres running with the project schema at `alembic upgrade head` (no new migration for this feature).
- Some organizations with Yandex reviews, and ideally a few days of `rating_snapshot` history for the trend blocks.
- An admin/operator login (the endpoint requires a session).

## Backend

```bash
cd apps/api
pip install -e ".[dev]"
pytest tests/test_dashboard_ratings.py -v     # this feature's critical-path tests
pytest -v                                     # full suite must stay green
uvicorn app.main:app --reload
```

Smoke the endpoint (authenticated session required):

```bash
# whole network, last 30 days
curl -b cookies.txt "http://localhost:8000/api/dashboard/ratings?period=30d&platform=all"

# single platform + custom range
curl -b cookies.txt "http://localhost:8000/api/dashboard/ratings?period=custom&date_from=2026-01-01&date_to=2026-03-31&platform=yandex"

# validation: expect 422
curl -b cookies.txt "http://localhost:8000/api/dashboard/ratings?period=custom"
curl -b cookies.txt "http://localhost:8000/api/dashboard/ratings?period=nonsense"
```

## Frontend

```bash
cd apps/web
npm install
npm run dev          # open http://localhost:3000/ratings
npm run lint
npm run test:e2e     # expects API + web running
```

## Validation scenarios

| # | Scenario | Expected outcome | Traces |
|---|---|---|---|
| 1 | Open `/ratings` with Yandex reviews present | Distribution table shows a Yandex row with avg rating, five star shares, and a removed count | US1, FR-002, FR-003 |
| 2 | Inspect the Google row | Aggregate avg rating shown; per-star and removed columns read «нет данных» (not `0`). Yandex and 2ГИС both show real breakdowns | US1, FR-004 |
| 3 | Sum a collected platform's per-star counts | Equals that platform's active review total | SC-002 |
| 4 | With ≥2 months of snapshots, view the dynamics and volume blocks | One monthly series per platform; months without snapshots appear as gaps, not zeros | US2, FR-005, FR-006 |
| 5 | With no snapshot history | Trend blocks show an "accruing" empty state, no error | US2 edge case, FR-011 |
| 6 | View the response-speed block with answered reviews | Weekly median and p95 series plotted against the fixed SLA target line | US3, FR-007 |
| 7 | View the weekday block | Seven rows Mon–Sun with counts and average ratings, plus a best/worst-day insight | US3, FR-008, FR-009 |
| 8 | Change period / platform / organization / company filters | Every block updates; no block keeps stale scope | FR-010, SC-003 |
| 9 | Reload the page after filtering | Filters restored from the URL | FR-012 |
| 10 | Apply an org filter matching nothing | All blocks show empty states; HTTP 200, no error | FR-011, SC-005 |
| 11 | Request `period=custom` without both dates, or reversed dates | API returns 422; the page falls back to defaults | Edge cases |
| 12 | Watch API logs / DB while loading the page | No writes, no scrape runs created | FR-013, SC-006 |
| 13 | Load the page for the full network | Renders in under 1 second | SC-004 |

## Verification gate

Per the project README: `pytest -v` in `apps/api`, then `npm run lint && npm run test:e2e` in `apps/web`. Additionally, the query-count guard in `test_dashboard_ratings.py` must show the SQL statement count unchanged as organization and review volume grow.
