# CSV Company/Organization Import Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A re-runnable script that loads `docs/companies_data.csv` into the DB — creating parent Companies (`RetailNetwork`) and Organization branches (every data row, including URL-less ones).

**Architecture:** Pure parsing helpers (CSV row → typed record) kept separate from the DB upsert layer, both in one importable module `scripts/import_companies_csv.py`. A thin `main()` wires argv → session → import. An additive Alembic migration makes `organizations.yandex_url` / `normalized_url` nullable so URL-less branches persist.

**Tech Stack:** Python 3.13, SQLAlchemy 2.0 ORM, Alembic, pytest (SQLite in-memory for tests), stdlib `csv`/`argparse`/`dataclasses`.

## Global Constraints

- Backend layering: reuse `app.services.url_utils` (`validate_yandex_url`, `normalize_yandex_url`, `extract_external_id`) — do not reimplement URL logic.
- Read-only product: script only writes `companies` / `organizations`; no scraping, no review changes.
- `JSON`/enum test compat: tests run on SQLite via `Base.metadata.create_all` (conftest `db_session` fixture) — model changes apply automatically to tests; the migration targets real Postgres.
- Idempotent: re-running must update, never duplicate. Company key = `name`; org key = `normalized_url` (URL rows) or `(company_id, name, city)` (URL-less rows).
- CSV facts: file `docs/companies_data.csv`, 2 header rows + 605 data rows, 16 cols. Columns: 0=BusinessRegion(city), 2=Department(org name), 3=RetailNetwork(company), 5=Yandex URL, 6=rating (`"4,2"`), 7=review count.

---

### Task 1: Nullable URL columns (model + migration)

**Files:**
- Modify: `apps/api/app/models/organization.py:17-18`
- Create: `apps/api/alembic/versions/0009_nullable_org_url.py`
- Test: `apps/api/tests/test_import_companies_csv.py`

**Interfaces:**
- Produces: `Organization.yandex_url: Mapped[str | None]`, `Organization.normalized_url: Mapped[str | None]` — later tasks insert orgs with these set to `None`.

- [ ] **Step 1: Write the failing test**

Create `apps/api/tests/test_import_companies_csv.py`:

```python
from app.models.organization import Organization


def test_organization_persists_with_null_urls(db_session):
    org = Organization(name="Сочи-04", city="Адлер", yandex_url=None, normalized_url=None)
    db_session.add(org)
    db_session.commit()
    db_session.refresh(org)
    assert org.id is not None
    assert org.yandex_url is None
    assert org.normalized_url is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/api && pytest tests/test_import_companies_csv.py::test_organization_persists_with_null_urls -v`
Expected: FAIL — `IntegrityError` / `NOT NULL constraint failed: organizations.yandex_url`.

- [ ] **Step 3: Make the columns nullable in the model**

In `apps/api/app/models/organization.py`, change lines 17-18 from:

```python
    yandex_url: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_url: Mapped[str] = mapped_column(Text, nullable=False)
```

to:

```python
    yandex_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    normalized_url: Mapped[str | None] = mapped_column(Text, nullable=True)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/api && pytest tests/test_import_companies_csv.py::test_organization_persists_with_null_urls -v`
Expected: PASS.

- [ ] **Step 5: Write the Alembic migration**

Create `apps/api/alembic/versions/0009_nullable_org_url.py`:

```python
"""make organizations.yandex_url / normalized_url nullable

Revision ID: 0009_nullable_org_url
Revises: 0008_companies
Create Date: 2026-07-10

Additive: URL-less branches (rows imported from companies_data.csv without a
valid Yandex Maps URL) are stored with NULL yandex_url/normalized_url.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0009_nullable_org_url"
down_revision: Union[str, None] = "0008_companies"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("organizations", "yandex_url", existing_type=sa.Text(), nullable=True)
    op.alter_column("organizations", "normalized_url", existing_type=sa.Text(), nullable=True)


def downgrade() -> None:
    op.alter_column("organizations", "normalized_url", existing_type=sa.Text(), nullable=False)
    op.alter_column("organizations", "yandex_url", existing_type=sa.Text(), nullable=False)
```

- [ ] **Step 6: Verify migration imports cleanly (no DB needed)**

Run: `cd apps/api && python -c "import importlib.util,glob; p=glob.glob('alembic/versions/0009_nullable_org_url.py')[0]; s=importlib.util.spec_from_file_location('m',p); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); print(m.revision, m.down_revision)"`
Expected: `0009_nullable_org_url 0008_companies`

- [ ] **Step 7: Commit**

```bash
git add apps/api/app/models/organization.py apps/api/alembic/versions/0009_nullable_org_url.py apps/api/tests/test_import_companies_csv.py
git commit -m "feat: nullable organization url columns for url-less imports"
```

---

### Task 2: CSV parsing helpers (pure, no DB)

**Files:**
- Create: `apps/api/scripts/__init__.py`
- Create: `apps/api/scripts/import_companies_csv.py`
- Test: `apps/api/tests/test_import_companies_csv.py`

**Interfaces:**
- Produces:
  - `@dataclass RowData(company_name: str, name: str, city: str, yandex_url: str | None, rating: float | None, review_count: int | None)`
  - `parse_rating(raw: str) -> float | None`
  - `parse_count(raw: str) -> int | None`
  - `select_yandex_url(raw: str) -> str | None` — returns the trimmed URL if `validate_yandex_url` accepts it, else `None`.
  - `parse_row(row: list[str]) -> RowData | None` — `None` when the row is blank or has an empty `RetailNetwork`.
  - `read_rows(path: str) -> list[RowData]` — skips the 2 header rows.
  - Column-index constants `COL_REGION=0, COL_NAME=2, COL_COMPANY=3, COL_URL=5, COL_RATING=6, COL_COUNT=7`.

- [ ] **Step 1: Write the failing tests**

Append to `apps/api/tests/test_import_companies_csv.py`:

```python
import pytest

from scripts.import_companies_csv import (
    RowData,
    parse_count,
    parse_rating,
    parse_row,
    select_yandex_url,
)


@pytest.mark.parametrize("raw,expected", [
    ("4,2", 4.2),
    ("5", 5.0),
    ("3.9", 3.9),
    ("-", None),
    ("-0", None),
    ("0", None),
    ("", None),
    ("  ", None),
])
def test_parse_rating(raw, expected):
    assert parse_rating(raw) == expected


@pytest.mark.parametrize("raw,expected", [
    ("18", 18),
    ("0", 0),
    ("", None),
    ("-", None),
    ("n/a", None),
])
def test_parse_count(raw, expected):
    assert parse_count(raw) == expected


def test_select_yandex_url_valid_canonical():
    url = "https://yandex.ru/maps/org/spoke/163787997704/"
    assert select_yandex_url(url) == url


def test_select_yandex_url_valid_shortlink():
    url = "https://yandex.by/maps/-/CPe4QI0P"
    assert select_yandex_url(url) == url


@pytest.mark.parametrize("raw", ["", "  ", "-", "https://go.2gis.com/Sf64K", "notaurl"])
def test_select_yandex_url_invalid_returns_none(raw):
    assert select_yandex_url(raw) is None


def test_parse_row_maps_columns():
    row = [""] * 16
    row[0] = "Адлер"
    row[2] = "Сочи-04 Адлер Ленина 73"
    row[3] = "SPOKE Россия"
    row[5] = "https://yandex.ru/maps/org/spoke/163787997704/"
    row[6] = "4,2"
    row[7] = "18"
    rd = parse_row(row)
    assert rd == RowData(
        company_name="SPOKE Россия",
        name="Сочи-04 Адлер Ленина 73",
        city="Адлер",
        yandex_url="https://yandex.ru/maps/org/spoke/163787997704/",
        rating=4.2,
        review_count=18,
    )


def test_parse_row_urlless_row():
    row = [""] * 16
    row[0] = "Москва"
    row[2] = "Точка-1"
    row[3] = "SPOKE Россия"
    rd = parse_row(row)
    assert rd is not None
    assert rd.yandex_url is None
    assert rd.rating is None
    assert rd.review_count is None


def test_parse_row_blank_or_no_company_returns_none():
    assert parse_row([""] * 16) is None
    row = [""] * 16
    row[2] = "Точка без компании"
    assert parse_row(row) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd apps/api && pytest tests/test_import_companies_csv.py -k "parse or select" -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts'`.

- [ ] **Step 3: Create the package marker and the module**

Create `apps/api/scripts/__init__.py` (empty file):

```python
```

Create `apps/api/scripts/import_companies_csv.py`:

```python
"""Import companies + organization branches from companies_data.csv.

Pure parsing helpers live here alongside the DB upsert layer and CLI. Reuses
app.services.url_utils for all Yandex URL handling. Idempotent: re-running
updates existing rows instead of inserting duplicates.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass

from app.services.url_utils import (
    extract_external_id,
    normalize_yandex_url,
    validate_yandex_url,
)

# CSV layout: 2 header rows, then data. 16 columns.
HEADER_ROWS = 2
COL_REGION = 0
COL_NAME = 2
COL_COMPANY = 3
COL_URL = 5
COL_RATING = 6
COL_COUNT = 7


@dataclass
class RowData:
    company_name: str
    name: str
    city: str
    yandex_url: str | None
    rating: float | None
    review_count: int | None


def parse_rating(raw: str) -> float | None:
    """'4,2' -> 4.2. Non-positive / out-of-range / junk -> None."""
    value = (raw or "").strip().replace(",", ".")
    if not value:
        return None
    try:
        rating = float(value)
    except ValueError:
        return None
    if rating <= 0 or rating > 5:
        return None
    return rating


def parse_count(raw: str) -> int | None:
    """Digits -> int (0 kept). Empty / non-numeric -> None."""
    value = (raw or "").strip()
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def select_yandex_url(raw: str) -> str | None:
    """Return the trimmed URL if it is a valid Yandex Maps URL, else None."""
    value = (raw or "").strip()
    if not value:
        return None
    try:
        validate_yandex_url(value)
    except ValueError:
        return None
    return value


def _cell(row: list[str], index: int) -> str:
    return row[index].strip() if len(row) > index else ""


def parse_row(row: list[str]) -> RowData | None:
    """Map one CSV data row to RowData. None if blank or no RetailNetwork."""
    company_name = _cell(row, COL_COMPANY)
    if not company_name:
        return None
    return RowData(
        company_name=company_name,
        name=_cell(row, COL_NAME),
        city=_cell(row, COL_REGION),
        yandex_url=select_yandex_url(_cell(row, COL_URL)),
        rating=parse_rating(_cell(row, COL_RATING)),
        review_count=parse_count(_cell(row, COL_COUNT)),
    )


def read_rows(path: str) -> list[RowData]:
    with open(path, encoding="utf-8", newline="") as handle:
        raw_rows = list(csv.reader(handle))
    parsed: list[RowData] = []
    for row in raw_rows[HEADER_ROWS:]:
        record = parse_row(row)
        if record is not None:
            parsed.append(record)
    return parsed
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd apps/api && pytest tests/test_import_companies_csv.py -k "parse or select" -v`
Expected: PASS (all parametrized cases).

- [ ] **Step 5: Commit**

```bash
git add apps/api/scripts/__init__.py apps/api/scripts/import_companies_csv.py apps/api/tests/test_import_companies_csv.py
git commit -m "feat: csv parsing helpers for company import"
```

---

### Task 3: DB import layer (company get-or-create + org upsert)

**Files:**
- Modify: `apps/api/scripts/import_companies_csv.py`
- Test: `apps/api/tests/test_import_companies_csv.py`

**Interfaces:**
- Consumes: `RowData` (Task 2), `normalize_yandex_url`, `extract_external_id`.
- Produces:
  - `@dataclass ImportSummary(companies_created, companies_found, orgs_inserted, orgs_updated, orgs_without_url, no_url_rows: list[tuple[str, str, str]])`
  - `import_rows(session, rows: list[RowData], dry_run: bool = False) -> ImportSummary` — commits on success; rolls back when `dry_run=True`.

- [ ] **Step 1: Write the failing tests**

Append to `apps/api/tests/test_import_companies_csv.py`:

```python
from app.models.company import Company
from scripts.import_companies_csv import ImportSummary, import_rows


def _rows():
    return [
        RowData("SPOKE Россия", "Сочи-04", "Адлер",
                "https://yandex.ru/maps/org/spoke/163787997704/", 4.2, 18),
        RowData("SPOKE Россия", "Москва-1", "Москва", None, None, None),
        RowData("Мир Суши Россия", "Казань-3", "Казань",
                "https://yandex.by/maps/-/CPFFmP9O", 3.7, 51),
    ]


def test_import_creates_companies_and_orgs(db_session):
    summary = import_rows(db_session, _rows())
    assert summary.companies_created == 2
    assert summary.orgs_inserted == 3
    assert summary.orgs_without_url == 1
    assert db_session.query(Company).count() == 2
    assert db_session.query(Organization).count() == 3


def test_import_sets_normalized_url_and_external_id(db_session):
    import_rows(db_session, _rows())
    org = db_session.query(Organization).filter(Organization.name == "Сочи-04").one()
    assert org.normalized_url == "https://yandex.ru/maps/org/spoke/163787997704"
    assert org.external_id == "163787997704"
    assert org.company.name == "SPOKE Россия"
    assert float(org.rating) == 4.2
    assert org.review_count == 18


def test_import_is_idempotent(db_session):
    import_rows(db_session, _rows())
    summary = import_rows(db_session, _rows())
    assert summary.companies_created == 0
    assert summary.companies_found == 2
    assert summary.orgs_inserted == 0
    assert summary.orgs_updated == 3
    assert db_session.query(Company).count() == 2
    assert db_session.query(Organization).count() == 3


def test_import_urlless_dedup_by_company_name_city(db_session):
    import_rows(db_session, _rows())
    # Same URL-less branch again with a changed rating -> update, not insert.
    again = [RowData("SPOKE Россия", "Москва-1", "Москва", None, 4.5, 9)]
    import_rows(db_session, again)
    urlless = db_session.query(Organization).filter(Organization.normalized_url.is_(None)).all()
    assert len(urlless) == 1
    assert urlless[0].review_count == 9


def test_import_dry_run_writes_nothing(db_session):
    summary = import_rows(db_session, _rows(), dry_run=True)
    assert summary.orgs_inserted == 3
    assert db_session.query(Company).count() == 0
    assert db_session.query(Organization).count() == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd apps/api && pytest tests/test_import_companies_csv.py -k import_ -v`
Expected: FAIL — `ImportError: cannot import name 'import_rows'`.

- [ ] **Step 3: Implement the import layer**

Add to `apps/api/scripts/import_companies_csv.py` (after `read_rows`, keeping the existing imports; add the two model imports at the top of the file):

```python
from app.models.company import Company
from app.models.enums import OrganizationScrapeStatus, ScrapeMode
from app.models.organization import Organization
```

```python
@dataclass
class ImportSummary:
    companies_created: int = 0
    companies_found: int = 0
    orgs_inserted: int = 0
    orgs_updated: int = 0
    orgs_without_url: int = 0
    no_url_rows: list[tuple[str, str, str]] = None  # (city, company, name)

    def __post_init__(self) -> None:
        if self.no_url_rows is None:
            self.no_url_rows = []


def _get_or_create_company(session, cache: dict[str, Company], name: str, summary: ImportSummary) -> Company:
    if name in cache:
        return cache[name]
    company = session.query(Company).filter(Company.name == name).first()
    if company is None:
        company = Company(name=name)
        session.add(company)
        session.flush()  # assign id
        summary.companies_created += 1
    else:
        summary.companies_found += 1
    cache[name] = company
    return company


def _upsert_org(session, company: Company, rd: RowData, summary: ImportSummary) -> None:
    if rd.yandex_url:
        normalized = normalize_yandex_url(rd.yandex_url)
        org = session.query(Organization).filter(Organization.normalized_url == normalized).first()
    else:
        normalized = None
        summary.orgs_without_url += 1
        summary.no_url_rows.append((rd.city, rd.company_name, rd.name))
        org = (
            session.query(Organization)
            .filter(
                Organization.company_id == company.id,
                Organization.name == rd.name,
                Organization.city == rd.city,
                Organization.normalized_url.is_(None),
            )
            .first()
        )

    if org is None:
        org = Organization(
            name=rd.name,
            city=rd.city,
            yandex_url=rd.yandex_url,
            normalized_url=normalized,
            external_id=extract_external_id(normalized) if normalized else None,
            rating=rd.rating,
            review_count=rd.review_count,
            company_id=company.id,
            preferred_scrape_mode=ScrapeMode.public,
            last_scrape_status=OrganizationScrapeStatus.pending,
        )
        session.add(org)
        session.flush()
        summary.orgs_inserted += 1
    else:
        org.name = rd.name
        org.city = rd.city
        org.company_id = company.id
        if rd.rating is not None:
            org.rating = rd.rating
        if rd.review_count is not None:
            org.review_count = rd.review_count
        summary.orgs_updated += 1


def import_rows(session, rows: list[RowData], dry_run: bool = False) -> ImportSummary:
    summary = ImportSummary()
    company_cache: dict[str, Company] = {}
    for rd in rows:
        company = _get_or_create_company(session, company_cache, rd.company_name, summary)
        _upsert_org(session, company, rd, summary)
    if dry_run:
        session.rollback()
    else:
        session.commit()
    return summary
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd apps/api && pytest tests/test_import_companies_csv.py -k import_ -v`
Expected: PASS (all 5 import tests).

- [ ] **Step 5: Run the full test file**

Run: `cd apps/api && pytest tests/test_import_companies_csv.py -v`
Expected: PASS (parsers + import + null-url model test).

- [ ] **Step 6: Commit**

```bash
git add apps/api/scripts/import_companies_csv.py apps/api/tests/test_import_companies_csv.py
git commit -m "feat: db upsert layer for company/organization import"
```

---

### Task 4: CLI entrypoint (`main` + `--dry-run` + summary)

**Files:**
- Modify: `apps/api/scripts/import_companies_csv.py`

**Interfaces:**
- Consumes: `read_rows`, `import_rows`, `ImportSummary` (Tasks 2-3), `app.core.database.SessionLocal`.
- Produces: `main(argv: list[str] | None = None) -> int` and a `if __name__ == "__main__"` guard.

- [ ] **Step 1: Implement `main` and the summary printer**

Add to the end of `apps/api/scripts/import_companies_csv.py`:

```python
def _print_summary(summary: ImportSummary, dry_run: bool) -> None:
    mode = "DRY RUN (nothing written)" if dry_run else "committed"
    print(f"Import {mode}:")
    print(f"  companies: {summary.companies_created} created, {summary.companies_found} found")
    print(f"  organizations: {summary.orgs_inserted} inserted, {summary.orgs_updated} updated")
    print(f"  organizations without URL: {summary.orgs_without_url}")
    if summary.no_url_rows:
        print("  URL-less branches (city | company | name):")
        for city, company, name in summary.no_url_rows:
            print(f"    - {city} | {company} | {name}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Import companies + branches from a CSV.")
    parser.add_argument("csv_path", help="Path to companies_data.csv")
    parser.add_argument("--dry-run", action="store_true", help="Parse and report without writing to the DB")
    args = parser.parse_args(argv)

    from app.core.database import SessionLocal

    rows = read_rows(args.csv_path)
    session = SessionLocal()
    try:
        summary = import_rows(session, rows, dry_run=args.dry_run)
    finally:
        session.close()
    _print_summary(summary, args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Verify the CLI parses and reports via dry-run (no DB write)**

Run: `cd apps/api && python -m scripts.import_companies_csv ../../docs/companies_data.csv --dry-run`
Expected: prints `Import DRY RUN (nothing written):` with `companies: ... created`, ~605 organizations inserted, ~29 organizations without URL, and a list of URL-less branches. Requires a reachable DB per `.env` (dry-run rolls back, writes nothing).

- [ ] **Step 3: Commit**

```bash
git add apps/api/scripts/import_companies_csv.py
git commit -m "feat: cli entrypoint for company import with --dry-run"
```

---

### Task 5: Apply migration + real import (operator run)

**Files:** none (execution only).

- [ ] **Step 1: Apply the migration**

Run: `cd apps/api && alembic upgrade head`
Expected: applies `0009_nullable_org_url`; `alembic current` shows `0009_nullable_org_url`.

- [ ] **Step 2: Dry-run against the real DB**

Run: `cd apps/api && python -m scripts.import_companies_csv ../../docs/companies_data.csv --dry-run`
Expected: summary shows ~605 orgs to insert, ~29 without URL, 5 companies created. Verify counts look right.

- [ ] **Step 3: Real import**

Run: `cd apps/api && python -m scripts.import_companies_csv ../../docs/companies_data.csv`
Expected: `Import committed:` with 5 companies created, ~576 orgs inserted with URL + ~29 without.

- [ ] **Step 4: Verify idempotency**

Run the same command again.
Expected: `0 created`, `5 found`, `0 inserted`, `~605 updated` — no new rows.

- [ ] **Step 5: Full backend test gate**

Run: `cd apps/api && pytest -v`
Expected: all tests pass (existing + new `test_import_companies_csv.py`).

---

## Notes for the implementer

- Run all commands from `apps/api` (pytest `pythonpath=["."]` makes `scripts` and `app` importable; the CSV lives two levels up at `../../docs/companies_data.csv`).
- The console on this Windows host garbles Cyrillic on `print`, but the DB stores UTF-8 correctly — judge correctness by DB counts, not console glyphs.
- Row counts (605 / 576 / 29 / 5) are the current CSV snapshot; treat them as sanity ranges, not hard assertions.
