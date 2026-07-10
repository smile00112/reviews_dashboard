# Bulk metrics-only scraper CLI — design

**Date:** 2026-07-10
**Status:** approved (brainstorming), pending implementation plan

## Goal

Collect **company rating + review count** for organizations already in the database
by following their platform links, from two platforms:

- **Yandex Maps** — `organizations.yandex_url` → `rating`, `review_count`
- **2GIS** — `organizations.gis2_url` → `gis2_rating`, `gis2_review_count`

Persist the freshly scraped values back onto the organization rows. Metrics only —
no individual reviews. First run is a **small test batch** to verify correctness and
proxy cost before any full run.

## Context

- DB is populated (~602 orgs; ~573 with `yandex_url`, ~547 with `gis2_url`). Migration
  `0010_multi_platform_metrics` is applied; per-platform columns exist.
- Existing scrapers are reused unchanged:
  - `app/scraper/yandex_http.py` `YandexHttpScraper` — browserless, no proxy cost.
  - `app/scraper/yandex_scrapeops.py` `YandexScrapeOpsScraper` — ScrapeOps proxy (paid).
  - `app/scraper/twogis_api.py` `TwogisApiScraper` — 2GIS catalog + reviews JSON APIs;
    short `go.2gis.com/CODE` links resolved via ScrapeOps proxy.
- Each scraper returns a `ScrapeResult` whose `.organization` (`ParsedOrganization`)
  carries `rating` and `review_count`. This design reads only `.organization` and
  ignores `.reviews`.

### Why a standalone CLI, not the `/scrape/all` API

`ScrapeService._scrape_organization` always passes `org.yandex_url` and
`_persist_scrape_result` always writes `result.organization.rating` / `review_count`
to the **Yandex** `rating` / `review_count` columns — regardless of mode. Routing a
2GIS run through it would (a) feed the wrong URL and (b) clobber the Yandex rating,
never touching `gis2_rating` / `gis2_review_count`. Fixing that means reworking the
tested review-persistence path. A metrics-only CLI sidesteps it entirely: it reads the
correct URL per platform and writes the correct columns, leaving the API and its
dedup/review code untouched.

## CLI

New file: `apps/api/scripts/scrape_metrics.py`, mirroring `scripts/import_companies_csv.py`
(argparse, `SessionLocal`, `--dry-run`).

```
python -m scripts.scrape_metrics [--platform {yandex,2gis,both}] [--limit N]
                                 [--only-missing] [--dry-run]
```

- `--platform` (default `both`) — which platform(s) to scrape.
- `--limit N` — cap number of orgs processed (test batch). Omit = all.
- `--only-missing` — skip orgs that already have a non-null metric for that platform.
- `--dry-run` — run scrapers and log outcomes, then `rollback()` (no DB writes).

## Flow

For each selected org, for each requested platform:

1. **Select URL**: yandex → `org.yandex_url`; 2gis → `org.gis2_url`. No URL → skip
   (count as skipped).
2. **Scrape**:
   - **Yandex**: `YandexHttpScraper().scrape(url)`. If it returns
     `needs_manual_action` or an error **and** `SCRAPEOPS_API_KEY` is set, fall back to
     `YandexScrapeOpsScraper().scrape(url)`.
   - **2GIS**: `TwogisApiScraper().scrape(url)`.
3. **Persist** (only on a clean result):
   - `needs_manual_action` → count `manual_action`, no write.
   - `error_code` set → count `failed`, no write.
   - `organization.rating is None` → count `failed` (nothing useful), no write.
   - Otherwise write the platform's rating + review_count columns. `review_count` is
     written only when non-null (never overwrite an existing count with null). Set
     `last_successful_scrape_at = now`, `last_scrape_status = success`.
4. Commit per org (so a mid-run crash keeps completed work). `--dry-run` rolls back
   at the end instead.

## Column mapping

| Platform | rating column | count column   |
|----------|---------------|----------------|
| yandex   | `rating`      | `review_count` |
| 2gis     | `gis2_rating` | `gis2_review_count` |

`yandex_rating_count` / `gis2_rating_count` (кол-во оценок, distinct from review count)
are **not** populated — the scrapers do not expose that figure separately. Left as-is.

## Overwrite policy

Fresh scraped values **overwrite** existing (CSV-imported) values by default.
`--only-missing` restricts a run to orgs whose target metric is currently null.

## Output

Per-platform summary printed at the end:

```
yandex:  updated=N failed=N manual_action=N skipped=N
2gis:    updated=N failed=N manual_action=N skipped=N
```

Plus a one-line-per-org progress log (name, platform, outcome, rating/count).

## Testing

- Unit test (SQLite, no network): a fake scraper injected into the persist helper —
  verify correct columns written per platform, null rating/count skipped, `--only-missing`
  and `--dry-run` honored. Follows `test_import_companies_csv.py` precedent.
- No live-network test in CI (constitution: scrapers are not exercised against real
  sites in tests).

## Out of scope

- Scraper internals / dedup / review persistence (unchanged).
- Google Maps metrics (no scraper; stays operator-editable).
- `metrics_only` optimization to skip review pagination — deferred; only worth adding
  before a full ~600-org run to cut wasted fetches. Test batch runs scrapers as-is.
```
