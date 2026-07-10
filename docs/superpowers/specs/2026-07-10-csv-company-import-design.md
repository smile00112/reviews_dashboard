# CSV Company/Organization Import — Design

**Date:** 2026-07-10
**Status:** Approved

## Goal

One-off, re-runnable script that reads `docs/companies_data.csv` and fills the
database: parent **Companies** (from `RetailNetwork`) and their **Organization**
branches (one per CSV data row that has a valid Yandex Maps URL).

## Source data

`docs/companies_data.csv` — 607 lines: 2 header rows + 605 data rows.
16 columns. Relevant columns (0-indexed):

| Col | CSV header      | Meaning                     |
|-----|-----------------|-----------------------------|
| 0   | BusinessRegion  | City of the organization    |
| 2   | Department      | Organization (branch) name  |
| 3   | RetailNetwork   | Company (parent) name       |
| 5   | ЯК              | Yandex Maps URL             |
| 6   | Рейтинг ЯК      | Yandex rating (`"4,2"`)     |
| 7   | количество      | Yandex review count         |

Observed: 5 distinct companies; 576/605 rows carry a valid Yandex URL
(327 canonical `/org/<slug>/<id>/`, rest short `yandex.by/maps/-/...`);
29 rows have no valid Yandex URL; 3 rows share a normalized URL with another
row (573 distinct organizations).

## Field mapping (per data row)

- `RetailNetwork` → `Company.name`
- `Department`    → `Organization.name`
- `BusinessRegion`→ `Organization.city`
- `ЯК` (col 5)    → `Organization.yandex_url` (+ `normalized_url`, `external_id`)
- `Рейтинг ЯК`    → `Organization.rating` — parse `"4,2"`→`4.2`; `-`, `-0`,
  empty → `null`
- `количество`    → `Organization.review_count` — int; empty/non-numeric → `null`
- `region`, `address` → left `null`
- `preferred_scrape_mode` = `public`, `last_scrape_status` = `pending`

## Behavior

Standalone script `apps/api/scripts/import_companies_csv.py`.
Run: `python -m scripts.import_companies_csv docs/companies_data.csv [--dry-run]`
(cwd = `apps/api`). Opens its own `SessionLocal`. Reuses
`app.services.url_utils` (`validate_yandex_url`, `normalize_yandex_url`,
`extract_external_id`).

Per data row:
1. **Company get-or-create** by exact `name` (trimmed). Cached in-process so the
   5 companies are resolved once.
2. **Yandex URL** from col 5, trimmed. If missing or `validate_yandex_url`
   rejects it → **skip the organization** (the company is still created) and
   record the row in a skipped list. → 29 skips expected.
3. **Organization upsert** keyed on `normalized_url`:
   - not present → insert (all mapped fields, `company_id` = resolved company).
   - present → update `name`, `city`, `rating`, `review_count`, `company_id`.
   The 3 duplicate-URL rows collapse onto the same organization (last wins).

**Idempotent:** re-running updates existing rows, never duplicates. Company keyed
by name, organization keyed by `normalized_url`.

## Output

Printed summary:
- companies created / found
- organizations inserted / updated
- rows skipped, with a list of `BusinessRegion | RetailNetwork | Department`
  and the skip reason (no URL / invalid URL)

`--dry-run`: parse, validate, and print the same summary **without** writing to
the database (no commit).

## Out of scope

- No Alembic migration (tables `companies`, `organizations` already exist).
- No scraping, no review dedup changes, no rating for 2GIS/Google columns.
- Not wired into the API or a scheduled job — manual operator script.
