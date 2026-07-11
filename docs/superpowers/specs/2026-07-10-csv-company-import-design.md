# CSV Company/Organization Import — Design

**Date:** 2026-07-10
**Status:** Approved

## Goal

One-off, re-runnable script that reads `docs/companies_data.csv` and fills the
database: parent **Companies** (from `RetailNetwork`) and their **Organization**
branches (one per CSV data row). Every data row becomes an organization —
including the 29 rows with no valid Yandex Maps URL.

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
- `ЯК` (col 5)    → `Organization.yandex_url` (+ `normalized_url`, `external_id`);
  missing/invalid → all three left `null`
- `Рейтинг ЯК`    → `Organization.rating` — parse `"4,2"`→`4.2`; `-`, `-0`,
  empty → `null`
- `количество`    → `Organization.review_count` — int; empty/non-numeric → `null`
- `region`, `address` → left `null`
- `preferred_scrape_mode` = `public`, `last_scrape_status` = `pending`

## Schema change (Alembic migration)

`organizations.yandex_url` and `organizations.normalized_url` are currently
`NOT NULL`. Add an additive migration making **both nullable** so URL-less
branches can be stored. Model (`app/models/organization.py`) updated to
`Mapped[str | None]` for both. Scrape flow already treats `pending` orgs as
not-yet-scraped; an org with `yandex_url IS NULL` is simply never dispatched to
a scraper (no code path forces a scrape on import).

## Behavior

Standalone script `apps/api/scripts/import_companies_csv.py`.
Run: `python -m scripts.import_companies_csv docs/companies_data.csv [--dry-run]`
(cwd = `apps/api`). Opens its own `SessionLocal`. Reuses
`app.services.url_utils` (`validate_yandex_url`, `normalize_yandex_url`,
`extract_external_id`).

Per data row:
1. **Company get-or-create** by exact `name` (trimmed). Cached in-process so the
   5 companies are resolved once.
2. **Yandex URL** from col 5, trimmed. If present and `validate_yandex_url`
   passes → set `yandex_url`, `normalized_url`, `external_id`. Otherwise
   (missing/invalid, ~29 rows) → leave all three `null` and record the row in a
   `no-url` list (reported, **not** skipped — the org is still created).
3. **Organization upsert:**
   - **has URL** → key on `normalized_url`. Not present → insert; present →
     update `name`, `city`, `rating`, `review_count`, `company_id`. The 3
     duplicate-URL rows collapse onto the same organization (last wins).
   - **no URL** → key on `(company_id, name, city)`. Not present → insert;
     present → update `rating`, `review_count`.

**Idempotent:** re-running updates existing rows, never duplicates. Company keyed
by name; organization keyed by `normalized_url` (URL rows) or
`(company_id, name, city)` (URL-less rows).

## Output

Printed summary:
- companies created / found
- organizations inserted / updated
- organizations stored without a URL, with a list of
  `BusinessRegion | RetailNetwork | Department` (reason: no/invalid URL)

`--dry-run`: parse, validate, and print the same summary **without** writing to
the database (no commit).

## Out of scope

- No new columns beyond the nullable change (tables `companies`,
  `organizations` already exist).
- No scraping, no review dedup changes, no rating for 2GIS/Google columns.
- Not wired into the API or a scheduled job — manual operator script.
