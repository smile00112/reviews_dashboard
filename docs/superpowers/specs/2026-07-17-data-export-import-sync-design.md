# Data export/import for cross-server sync

## Problem

The dashboard's data (companies, organizations/branches, reviews) lives in one
Postgres instance. There's a need to move this data to another server —
setting up a staging/replica environment, or migrating to new infrastructure —
and to be able to repeat the transfer later and pick up only what changed,
without re-scraping everything from Yandex on the new server.

Baking data directly into an Alembic migration (the pattern used by
`0009_seed_sushi_master.py` for 209 organizations) does not scale here: the
current database holds 5 companies, 602 organizations, and 52,620 reviews.
Literal Python data of that size in a migration file is impractical to author,
review, and diff.

## Approach

Two new CLI scripts under `apps/api/scripts/`, following the existing pattern
of `export_reviews_csv.py` / `import_companies_csv.py`: standalone scripts
using `argparse`, `SessionLocal`, and a `--dry-run` flag, invoked as
`python -m scripts.<name>`.

### `export_data.py`

Reads `companies`, `organizations`, `reviews` from the source DB and writes
three JSON Lines files (one JSON object per row, one row per line — streams
without loading the full result set into memory, and is line-diffable):

```
apps/api/data_export/companies.jsonl
apps/api/data_export/organizations.jsonl
apps/api/data_export/reviews.jsonl
```

Every column is serialized as-is, including `id` (UUID → string, `datetime`/
`date` → ISO 8601 string, `Decimal`/`Numeric` → float). Queries use
`yield_per()` so `reviews.jsonl` (tens of thousands of rows) streams to disk
rather than materializing a Python list of ORM objects.

CLI: `python -m scripts.export_data [--out-dir apps/api/data_export]`.
Prints a row-count summary per file.

The output directory is added to `.gitignore` (same treatment as
`apps/api/reports/` for `export_reviews_csv.py`) — review text includes
author names, so exported data must not land in the git history. Operators
move the three files to the target server by whatever channel they choose
(scp, S3, etc.) — that transfer step is out of scope for these scripts.

### `import_data.py`

Reads the three JSONL files and **upserts by `id`** into the target DB, in
strict order `companies → organizations → reviews` (required by FK
dependencies: `organizations.company_id`, `reviews.organization_id`).

For each entity, in batches:
1. Query the target DB for which incoming `id`s already exist (chunked
   `IN (...)`, not one query per row).
2. Existing ids → `UPDATE` every column to the file's value. Missing ids →
   `INSERT` a new row with that exact `id`.
3. Review inserts are wrapped in a `SAVEPOINT` per row (`db.begin_nested()`),
   mirroring `ReviewService.upsert_reviews` — a single bad/duplicate row
   rolls back only itself, not the whole batch.

Because rows are matched on the source's stable `id` (preserved verbatim,
not regenerated), the script is idempotent: rerunning against the same or an
updated export file only inserts new rows and updates changed columns. This
is a full-column overwrite on conflict — the target ends up mirroring the
source's exported state for every column, including operator-edited fields
(`status`, `is_paid`, `reply_text`, `reply_at`, ...). That is the intended
"sync" semantics: pushing a fresh export always makes the target match the
source, not a field-by-field merge that tries to preserve target-side edits.

CLI: `python -m scripts.import_data --dir apps/api/data_export [--dry-run]`.
`--dry-run` parses and prints the same created/updated summary per table but
rolls back instead of committing.

### Out of scope

- Incremental/date-filtered export.
- `scrape_runs` / `rating_snapshot` history (operational data, not needed to
  bootstrap or sync a target server's org/review dataset).
- Compression or encryption of the export files.
- Automating the file transfer between servers.

## Testing

`apps/api/tests/test_export_import_data.py`, matching the constitution's
"critical-path tests required" bar:

- Export then import into an empty (SQLite) session reproduces the source
  rows.
- Re-importing the same file is a no-op for row counts (no duplicates) and
  correctly applies column changes when the file's content differs from
  what's already in the target (update path).
- Import order is FK-safe: an `organizations.jsonl` referencing a
  `company_id` only present in `companies.jsonl` imports cleanly when
  companies are processed first.
