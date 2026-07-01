# Data Model: HTTP Review Scraper

**Feature**: `003-http-scraper` | **Date**: 2026-06-30

No new tables. No new columns. The only schema change is one new value on the scrape-mode
enum type(s).

## Modified: scrape-mode enum

`ScrapeMode` (Python, `models/enums.py`) gains:

| Value | Meaning |
|-------|---------|
| `public_http` | Browserless HTTP scrape (requests + BeautifulSoup, `?page=N` pagination) |

Existing values `public`, `operator_auth` are unchanged.

Postgres: `ALTER TYPE scrape_mode_enum ADD VALUE IF NOT EXISTS 'public_http'` and likewise
for `review_scrape_mode_enum` (the enum used by `reviews.scrape_mode`). `ADD VALUE` cannot
run inside a transaction block on older PG; the migration commits per statement
accordingly. SQLite (tests) stores the value as plain text — no migration needed there.

## Reused unchanged

- **ScrapeRun**: one row per HTTP scrape attempt, `mode=public_http`, same status lifecycle
  (`queued → running → success | failed | needs_manual_action`), same counts/timestamps,
  same `debug_html_path` (populated on bot-detection).
- **Review**: rows tagged `scrape_mode=public_http`; identical dedup (`content_hash`) and
  feature-002 analytics columns. No structural change.

## Invariants

- Adding `public_http` MUST NOT change behavior of existing modes or existing rows.
- HTTP-scraped reviews participate in the same per-organization dedup as Playwright-scraped
  reviews (the same review seen via `public` and `public_http` dedups to one row, since the
  hash inputs — author/rating/date-text/text — are mode-independent).
