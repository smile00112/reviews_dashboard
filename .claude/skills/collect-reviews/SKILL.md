---
name: collect-reviews
description: Use when collecting/scraping organization reviews from Yandex Maps or 2GIS into the database - covers the scrape_reviews CLI, platform/mode choice, review caps, and how to read the outcome. Triggers on "собери отзывы", "collect reviews", "scrape reviews for org", "обнови отзывы".
---

# Collecting organization reviews

Run the collector from `apps/api`:

```bash
cd apps/api
python -m scripts.scrape_reviews --org-id <uuid> [options]
python -m scripts.scrape_reviews --all [options]
```

`--org-id` and `--all` are mutually exclusive; exactly one is required.

## Picking flags

| Goal | Flags |
|---|---|
| One org, Yandex, default cap (150) | `--org-id <uuid>` |
| One org, every review available | `--org-id <uuid> --all-reviews` |
| All orgs, 2GIS | `--all --platform 2gis` |
| Test batch of 5 orgs | `--all --limit 5` |
| Preview the plan (scrapes nothing) | `--dry-run` |
| Long run you want to watch | `--log-file` (bare flag → `logs/scrape_reviews_<ts>.log`) |

`--limit`/`--offset` count **organizations**, not reviews. Review volume is
controlled by `--all-reviews` alone.

`--dry-run` prints which orgs would be scraped, with the resolved mode and URL. It
does **not** scrape-then-roll-back: `ScrapeService` commits its own writes, so there
would be nothing left to undo. To rehearse a real collection cheaply, use
`--limit 1..5` instead.

## Platform → mode

`--platform` picks both the URL column and the default mode. `--mode` overrides it;
a mode from the other platform is rejected at startup.

- `yandex` (default) → `public_http`, reads `organizations.yandex_url`
- `2gis` → `twogis_api`, reads `organizations.gis2_url`

**Do not switch Yandex to `--mode public` to "get more reviews".** `public` drives
headless Chromium, and Chromium cannot authenticate against the SOCKS5 proxy pool
(`Browser does not support socks5 proxy authentication`). Without a proxy, Yandex
rate-limits this machine's IP with HTTP 429 and the run ends `needs_manual_action`.
`public_http` is the only Yandex mode that routes through `PROXY_POOL`.
`--all-reviews` is rejected for `public`/`operator_auth` — they scroll rather than
paginate and have no cap to lift.

## Known ceiling: ~600 reviews per Yandex org

Yandex serves at most **12 pages of `?page=N` (~600 reviews)**; page 13 returns
HTTP 200 with zero review blocks. So an org showing 1110 reviews on the site yields
600 via `public_http` even with `--all-reviews` — verified 2026-07-16 on
`007cab4a-…` (sushi_master/127725206638).

This is a platform limit, **not a bug and not something `--all-reviews` can fix**.
The remaining reviews live behind the SPA's infinite scroll, reachable only by the
Playwright modes, which cannot use the proxy pool (see above). If a run reports fewer
reviews than the org's `review_count`, check this before investigating.

## Reading the outcome

Each org gets its own `ScrapeRun` row; the CLI prints one line per org plus a summary.

- `success` — reviews collected. `inserted` vs `updated` reflects the `content_hash`
  dedup: re-scraping an org updates `last_seen_at` instead of duplicating rows, so a
  second run legitimately shows `inserted=0`.
- `needs_manual_action` — captcha / bot wall / **HTTP 429 rate-limit**. Not a failure;
  no retry loop, no bypass. Check `error_message` and the saved debug artifacts.
- `failed` — `no_url` means the org has no link for that platform; it is skipped
  before any scraper call.
- `skip (no <platform> url)` — org lacks the platform link entirely.

**A `success` with 0 reviews is suspicious.** Historically a 429 was reported as
exactly that (fixed 2026-07-16 by checking the HTTP status, not just page text).
If you see it, verify the page rather than concluding the org has no reviews.

## Org info is refreshed automatically

Every successful scrape also writes the org's name, rating, review_count,
rating_count and address via `OrganizationService.update_scrape_status`, into that
platform's own columns (`rating`/`review_count` for Yandex, `gis2_*` for 2GIS), plus
a daily rating snapshot. No separate command is needed for that.

For metrics **without** reviews, use `python -m scripts.scrape_metrics` instead.

## Verify after changing the collector

```bash
cd apps/api && pytest -q
```
