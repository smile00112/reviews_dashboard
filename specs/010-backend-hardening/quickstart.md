# Quickstart Validation: Backend Hardening (010)

## Prerequisites

```bash
cd apps/api
pip install -e ".[dev]"
alembic upgrade head        # applies 0013 (indexes + session_status 'pending')
```

## 1. Full regression gate

```bash
pytest -v
```

Expected: all pre-existing tests pass unchanged (dedup contract intact) plus new suites:
`test_review_upsert_concurrency.py`, `test_scrape_all_aggregation.py`,
`test_scraper_session_async.py`, `test_markers.py`, `test_cors_config.py`,
extended `test_twogis_api.py`.

## 2. Targeted checks

```bash
pytest tests/test_review_deduplication.py -v          # contract frozen
pytest tests/test_review_upsert_concurrency.py -v     # US1: no batch loss, exact counters
pytest tests/test_scrape_all_aggregation.py -v        # US2: parent status matrix + roll-up
pytest tests/test_scraper_session_async.py -v         # US3: immediate 202 + pending
pytest tests/test_twogis_api.py -v                    # US6: rating<1 dropped
```

## 3. Manual smoke (running stack)

```bash
docker compose up --build
```

- `POST http://localhost:8000/api/scraper/yandex/login` → responds < 1 s with `{"status": "pending", ...}`; `GET .../session` eventually shows terminal status (US3 / SC-003).
- `POST http://localhost:8000/api/scrape/all {"mode": "public"}` with all orgs behind captcha → parent run in `GET /api/scrape-runs` shows `needs_manual_action`, not `success` (US2 / SC-002).
- API logs (docker) show `WARNING`/`ERROR` lines with org/run context on scrape or snapshot failures — no silent failures (SC-006).
- Set `API_CORS_ORIGINS=` (empty) in `.env` → API refuses to start with explicit config error (US6 / FR-013).

## 4. Migration check (Postgres)

```bash
alembic upgrade head && alembic downgrade -1 && alembic upgrade head
psql ... -c "\d reviews"   # shows ix_reviews_org_review_date / _first_seen / _platform
```

Note: `ALTER TYPE ... ADD VALUE` is irreversible on Postgres — the 0013 downgrade only drops indexes and leaves the enum value (documented in the migration docstring).

## References

- Decisions: [research.md](research.md)
- Entity/state changes: [data-model.md](data-model.md)
- Endpoint semantics: [contracts/api-deltas.md](contracts/api-deltas.md)
