# Quickstart: Dashboard Overview Performance validation

**Feature**: 012-dashboard-overview-perf

## Prerequisites

- `apps/api`: `pip install -e ".[dev]"`, migrations applied (`alembic upgrade head` — must include `0017_dashboard_overview_indexes`).
- For live timing: full stack running (Postgres + API), DB populated with real scraped data.

## 1. Behavioral contract (must pass unmodified)

```bash
cd apps/api
pytest tests/test_dashboard_overview.py tests/test_dashboard_attention_rules.py -v
pytest tests/test_query_counts.py -v
pytest -v   # full suite gate before merge
```

Expected: green with **zero edits** to the two dashboard suites; query-count test includes the new does-not-scale-with-reviews case.

## 2. Migration check

```bash
cd apps/api
alembic upgrade head
alembic downgrade -1 && alembic upgrade head   # 0017 is reversible
```

Expected: indexes `ix_reviews_org_unanswered` (partial) and `ix_reviews_org_platform_first_seen` exist on `reviews`.

## 3. Live timing (SC-001, SC-004)

```bash
# default view
curl -s -o /dev/null -w "%{time_total}\n" -b "<auth cookie>" \
  "http://localhost:8000/api/dashboard/overview?period=30d&platform=all"
# platform-filtered must not be slower
curl -s -o /dev/null -w "%{time_total}\n" -b "<auth cookie>" \
  "http://localhost:8000/api/dashboard/overview?period=30d&platform=yandex"
```

Expected: < 0.3 s each on production-scale data (was ~5 s).

## 4. Payload identity spot-check (SC-002)

Before starting implementation, capture a baseline against the same DB:

```bash
curl -s -b "<auth cookie>" "http://localhost:8000/api/dashboard/overview?period=30d&platform=all" | jq 'del(.generated_at)' > /tmp/overview_before.json
# ... after implementation, same DB state:
curl -s -b "<auth cookie>" "http://localhost:8000/api/dashboard/overview?period=30d&platform=all" | jq 'del(.generated_at)' > /tmp/overview_after.json
diff /tmp/overview_before.json /tmp/overview_after.json   # expected: empty
```

Repeat for `period=all`, `platform=yandex`, a `company_id` filter.

## 5. Index usage (optional, PG only)

```sql
EXPLAIN ANALYZE SELECT organization_id, count(*) FROM reviews
WHERE response_text IS NULL AND organization_id IN ('<org-uuid>') GROUP BY organization_id;
```

Expected: partial index `ix_reviews_org_unanswered` in the plan; no seq scan on `reviews` for the aggregate queries.
