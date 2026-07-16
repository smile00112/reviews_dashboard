---
name: export-reviews-csv
description: Use when the user wants reviews (and company responses) exported to CSV for a date range - a report/download of Yandex (or 2GIS/Google) reviews. Triggers on "экспорт отзывов в csv", "выгрузи отзывы", "отчет по отзывам за период", "export reviews csv", "csv с отзывами и ответами", or any request for a review report/spreadsheet covering a date range. Make sure to use this whenever the user asks for reviews "in CSV", "as a spreadsheet", or "for a period/range", even if they don't say the word "export".
---

# Exporting reviews to CSV

Run from `apps/api`:

```bash
cd apps/api
python -m scripts.export_reviews_csv --start YYYY-MM-DD --end YYYY-MM-DD [--platform yandex|google|gis2] [--out path.csv]
```

Both `--start` and `--end` are inclusive and required. `--platform` defaults to
`yandex`. Without `--out`, the file lands at
`apps/api/reports/<platform>_reviews_<start>_<end>.csv` (gitignored — treat
`reports/` as scratch, not something to commit).

The script (`apps/api/scripts/export_reviews_csv.py`) is read-only: one SELECT
joining `reviews` + `organizations` via the app's own `SessionLocal` (so it picks
up `DATABASE_URL` from `.env` automatically — no need to hand-roll a DB connection
or hunt for credentials). Filters on `Review.platform` and
`review_date BETWEEN start AND end`, ordered by organization then date.

## Output columns

`organization, author_name, rating, review_date, review_text, response_text`

`response_text` is the business's reply, stored read-only (see
`build_review_hash` / dedup notes in the project's CLAUDE.md) — it is never
posted back to Yandex, just displayed. Empty string means no reply on file for
that review.

## Turning a natural-language date range into `--start`/`--end`

Users usually give the range conversationally ("с 15 июня по 15 июля", "last
month", "May 15 to June 15"). Resolve it to two `YYYY-MM-DD` values yourself
before calling the script — don't ask the user to reformat it. Anchor relative
phrasing ("last month", "this week") to the current date from context.

## After running

Report the row count the script prints and the output path. If the count seems
surprisingly low for the range, it likely means most reviews in that window
belong to a different `platform` than requested, or the range predates when
those organizations were first scraped — not a bug in the script.
