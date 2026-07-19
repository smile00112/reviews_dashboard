# Quickstart Validation: Review Removal Sync

## Prerequisites

```bash
cd apps/api
pip install -e ".[dev]"
alembic upgrade head          # applies 0016 (reviews.removed_at, scrape_runs.full_pass)
```

## Automated tests (critical path — must pass before merge)

```bash
cd apps/api
pytest tests/test_review_removal.py -v      # marking / un-marking / scoping / zero-guard
pytest tests/test_scraper_full_pass.py -v   # per-scraper full_pass semantics
pytest tests/test_job_runner.py -v          # extended decision matrix (!=, forced refresh)
pytest tests/test_review_deduplication.py -v  # contract unchanged
pytest -v                                   # full suite
cd ../web && npm run lint && npm run test:e2e
```

Scenario coverage expected from the suites (maps to spec acceptance scenarios):

| Scenario | Expectation |
|---|---|
| Full pass missing one known review | that review gets `removed_at`; others untouched; non-removed count == platform counter |
| Partial pass (limit hit / max_pages hit / skipped page / error / needs_manual_action) | zero rows marked removed |
| Removed review reappears | same row un-marked (`removed_at=NULL`), no new row inserted |
| Full pass returns 0 with collected reviews present, counter ≠ 0 | run `failed`, `error_code=empty_full_pass`, nothing marked |
| Full pass returns 0, platform counter == 0 | all marked removed (legitimate wipe-out) |
| Yandex pass | never touches `gis2` rows of the same org |
| Job decision: platform 12 vs 10 non-removed | scrape |
| Job decision: platform 8 vs 10 non-removed | scrape (was: skip) |
| Job decision: platform 10 vs 10 non-removed (+2 removed) | skip "counters match" |
| Counter `None` | skip with metrics-first reason (unchanged) |
| `force_full_every_days=7`, counters match, last full pass 8 days old | scrape with forced-refresh reason |
| `force_full_every_days` absent | identical to plain `!=` rule |

## Manual end-to-end (dev stack)

1. Start the stack (see `run-local-stack` skill or `docker compose up --build`).
2. Seed/pick an org with collected Yandex reviews; note `GET /api/organizations/{id}` counters.
3. Trigger the reviews job (`POST /api/jobs/{id}/run`, admin) and inspect `GET /api/jobs/runs/{run_id}`: item payload shows `platform_total` vs `scraped_before`, and the linked scrape run shows `full_pass: true` when pagination exhausted.
4. Delete-simulation: lower the org's platform counter in DB (or wait for a real removal), re-run the job → scrape triggers, review gets `removed_at`, default list `GET /api/organizations/{id}/reviews` no longer shows it, `?removed=removed` does.
5. Web: org reviews page → "show removed" toggle displays the review with a removal badge + date.

## Production schedule application (FR-009 — config only)

For each of the four jobs (`org_metrics`/`reviews` × `yandex`/`gis2`), as admin:

```bash
# metrics — twice daily, Europe/Moscow
PATCH /api/jobs/{metrics_job_id}   {"schedule_cron": "0 4,16 * * *", "is_enabled": true}
# reviews — one hour after each metrics cycle
PATCH /api/jobs/{reviews_job_id}   {"schedule_cron": "0 5,17 * * *", "is_enabled": true}
```

Verify next morning/afternoon in `/jobs`: two runs per job per day; reviews runs see counters refreshed by the same cycle's metrics run. Overlap protection (409 while a run is active) is pre-existing.
