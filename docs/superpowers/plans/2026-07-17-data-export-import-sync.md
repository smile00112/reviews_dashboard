# Data Export/Import Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Two CLI scripts that let an operator dump companies/organizations/reviews to disk and idempotently sync them into another server's database, without baking tens of thousands of rows into an Alembic migration.

**Architecture:** `apps/api/scripts/export_data.py` streams the three tables to JSON Lines files (one JSON object per row, `id` included as-is). `apps/api/scripts/import_data.py` reads those files back and upserts every row into the target DB **by primary key `id`** (insert if absent, full-column overwrite if present), in FK-safe order `companies → organizations → reviews`. Both follow the existing `apps/api/scripts/*.py` CLI pattern (`argparse`, `SessionLocal`, `--dry-run`).

**Tech Stack:** Python 3.12, SQLAlchemy ORM (`Session.query`), existing models (`Company`, `Organization`, `Review`), pytest with the repo's `db_session` SQLite fixture.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-17-data-export-import-sync-design.md`.
- Output files are JSON Lines (`companies.jsonl`, `organizations.jsonl`, `reviews.jsonl`), one JSON object per line, written/read from a directory (default `data_export/`, relative to the `apps/api` working directory scripts already run from — see `README`/other scripts' `reports/` convention).
- Row matching for upsert is **by `id`** (the exported UUID primary key is preserved verbatim on the target) — not by natural key, not by `content_hash`. Every column present in the export overwrites the target row's column on conflict; this is a full sync, not a selective merge.
- `Review.paid_marked_by_user_id` and `Review.replied_by_user_id` are **deliberately excluded** from both export and import: they are foreign keys to `users`, and `app/scripts/seed_users.py` generates a fresh random `id` per server, so a source-server user id would violate the target's FK on insert. `status`, `is_paid`, `paid_cost`, `reply_text`, `reply_at` (the non-FK admin fields) are still carried over.
- `scrape_runs` and `rating_snapshot` are out of scope (operational history, not needed to bootstrap/sync a target's org+review dataset).
- The output directory (`apps/api/data_export/`) must be gitignored — reviews contain author names and must not enter git history.
- Reviews are exported with `Query.yield_per()` so the ~50k-row table streams to disk instead of loading fully into memory.
- Tests use the repo's existing `db_session` pytest fixture (SQLite, `apps/api/tests/conftest.py`) and call the export/import functions directly (not by shelling out to the CLI), matching `tests/test_import_companies_csv.py`'s style.

---

### Task 1: `export_data.py` — dump companies/organizations/reviews to JSONL

**Files:**
- Create: `apps/api/scripts/export_data.py`
- Modify: `.gitignore` (repo root) — add `apps/api/data_export/`
- Test: `apps/api/tests/test_export_data.py`

**Interfaces:**
- Consumes: `app.core.database.SessionLocal`, `app.models.company.Company`, `app.models.organization.Organization`, `app.models.review.Review`.
- Produces (for Task 2 and for tests):
  - `COMPANY_FIELDS: list[str]`, `ORGANIZATION_FIELDS: list[str]`, `REVIEW_FIELDS: list[str]` — canonical column-name lists (Task 2's `import_data.py` field lists must match these exactly, field-for-field, since a mismatch silently drops or omits data on import).
  - `serialize_row(obj, fields: list[str]) -> dict` — converts one ORM object's listed columns to JSON-safe values.
  - `export_companies(db: Session, out_path: Path) -> int`, `export_organizations(db: Session, out_path: Path) -> int`, `export_reviews(db: Session, out_path: Path) -> int` — each writes one JSONL file, returns row count written.

- [ ] **Step 1: Write the failing test for `serialize_row` type coercion**

Create `apps/api/tests/test_export_data.py`:

```python
import json
from datetime import date, datetime, timezone
from uuid import uuid4

from app.models.company import Company
from app.models.enums import OrganizationScrapeStatus, ScrapeMode
from app.models.organization import Organization
from app.models.review import Review
from scripts.export_data import (
    COMPANY_FIELDS,
    ORGANIZATION_FIELDS,
    REVIEW_FIELDS,
    export_companies,
    export_organizations,
    export_reviews,
    serialize_row,
)


def test_serialize_row_coerces_uuid_datetime_decimal():
    company = Company(id=uuid4(), name="Acme", is_active=True)
    company.created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    company.updated_at = datetime(2026, 1, 2, tzinfo=timezone.utc)
    row = serialize_row(company, COMPANY_FIELDS)
    assert row["id"] == str(company.id)
    assert row["created_at"] == "2026-01-01T00:00:00+00:00"
    # JSON-round-trippable
    json.dumps(row)


def test_export_companies_writes_one_line_per_row(db_session, tmp_path):
    db_session.add_all([Company(name="Acme"), Company(name="Beta")])
    db_session.commit()

    out_path = tmp_path / "companies.jsonl"
    count = export_companies(db_session, out_path)

    assert count == 2
    lines = out_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    names = {json.loads(line)["name"] for line in lines}
    assert names == {"Acme", "Beta"}


def test_export_organizations_includes_enum_and_platform_fields(db_session, tmp_path):
    org = Organization(
        name="Point 1",
        yandex_url="https://yandex.ru/maps/org/x/1/",
        normalized_url="https://yandex.ru/maps/org/x/1",
        external_id="1",
        rating=4.5,
        preferred_scrape_mode=ScrapeMode.public,
        yandex_scrape_status=OrganizationScrapeStatus.success,
    )
    db_session.add(org)
    db_session.commit()

    out_path = tmp_path / "organizations.jsonl"
    count = export_organizations(db_session, out_path)

    assert count == 1
    row = json.loads(out_path.read_text(encoding="utf-8").strip())
    assert row["preferred_scrape_mode"] == "public"
    assert row["yandex_scrape_status"] == "success"
    assert row["rating"] == 4.5
    assert set(ORGANIZATION_FIELDS) == set(row.keys())


def test_export_reviews_streams_all_rows(db_session, tmp_path):
    org = Organization(name="Point 1")
    db_session.add(org)
    db_session.commit()
    db_session.add(
        Review(
            organization_id=org.id,
            scrape_mode=ScrapeMode.public,
            rating=5,
            review_text="Great",
            content_hash="hash1",
            review_date=date(2026, 1, 1),
        )
    )
    db_session.commit()

    out_path = tmp_path / "reviews.jsonl"
    count = export_reviews(db_session, out_path)

    assert count == 1
    row = json.loads(out_path.read_text(encoding="utf-8").strip())
    assert row["review_text"] == "Great"
    assert row["review_date"] == "2026-01-01"
    assert "paid_marked_by_user_id" not in row
    assert "replied_by_user_id" not in row
    assert set(REVIEW_FIELDS) == set(row.keys())
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd apps/api && pytest tests/test_export_data.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.export_data'`

- [ ] **Step 3: Implement `apps/api/scripts/export_data.py`**

```python
"""Export companies, organizations, and reviews to JSON Lines files for cross-server
sync (see import_data.py). Read-only: uses SessionLocal directly, no DB writes.

Reviews are streamed with yield_per() so exporting tens of thousands of rows does not
hold the full result set in memory.
"""

from __future__ import annotations

import argparse
import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.company import Company
from app.models.organization import Organization
from app.models.review import Review

COMPANY_FIELDS = ["id", "name", "is_active", "created_at", "updated_at"]

ORGANIZATION_FIELDS = [
    "id", "name", "yandex_url", "normalized_url", "external_id", "address",
    "rating", "review_count", "yandex_rating_count",
    "gis2_url", "gis2_rating", "gis2_review_count", "gis2_rating_count",
    "google_url", "google_rating", "google_review_count", "google_rating_count",
    "preferred_scrape_mode", "yandex_scrape_status", "gis2_scrape_status",
    "yandex_last_successful_scrape_at", "gis2_last_successful_scrape_at",
    "city", "region", "is_franchise", "company_id", "created_at", "updated_at",
]

# paid_marked_by_user_id / replied_by_user_id are intentionally excluded: they are
# foreign keys to source-server-local user accounts (app/scripts/seed_users.py mints
# a fresh random id per server) and would violate the target's users FK on import.
REVIEW_FIELDS = [
    "id", "organization_id", "source", "scrape_mode", "external_review_id",
    "author_name", "rating", "review_text", "review_date_text", "review_date",
    "response_text", "response_first_seen_at", "content_hash",
    "first_seen_at", "last_seen_at",
    "status", "is_paid", "platform", "paid_cost",
    "reply_text", "reply_at",
    "sentiment", "sentiment_score", "sentiment_confidence", "rating_sentiment_mismatch",
    "problems", "analyzed_at",
]


def _jsonable(value):
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def serialize_row(obj, fields: list[str]) -> dict:
    return {field: _jsonable(getattr(obj, field)) for field in fields}


def _write_jsonl(rows, fields: list[str], out_path: Path) -> int:
    count = 0
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for obj in rows:
            f.write(json.dumps(serialize_row(obj, fields), ensure_ascii=False))
            f.write("\n")
            count += 1
    return count


def export_companies(db: Session, out_path: Path) -> int:
    query = db.query(Company).order_by(Company.id)
    return _write_jsonl(query, COMPANY_FIELDS, out_path)


def export_organizations(db: Session, out_path: Path) -> int:
    query = db.query(Organization).order_by(Organization.id)
    return _write_jsonl(query, ORGANIZATION_FIELDS, out_path)


def export_reviews(db: Session, out_path: Path) -> int:
    query = db.query(Review).order_by(Review.id).yield_per(1000)
    return _write_jsonl(query, REVIEW_FIELDS, out_path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Export companies/organizations/reviews to JSONL for cross-server sync (see import_data.py)."
    )
    parser.add_argument(
        "--out-dir", type=Path, default=Path("data_export"), help="Output directory (default: data_export)"
    )
    args = parser.parse_args(argv)

    from app.core.database import SessionLocal

    db = SessionLocal()
    try:
        counts = {
            "companies": export_companies(db, args.out_dir / "companies.jsonl"),
            "organizations": export_organizations(db, args.out_dir / "organizations.jsonl"),
            "reviews": export_reviews(db, args.out_dir / "reviews.jsonl"),
        }
    finally:
        db.close()

    for name, count in counts.items():
        print(f"{name}: {count} rows -> {args.out_dir / f'{name}.jsonl'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Add the output directory to `.gitignore`**

Edit `.gitignore` (repo root), in the same block as the existing `apps/api/reports/` entry:

```
# Ad-hoc CSV exports (export_reviews_csv.py)
apps/api/reports/

# Cross-server data sync exports (export_data.py) - contains reviewer PII
apps/api/data_export/
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd apps/api && pytest tests/test_export_data.py -v`
Expected: PASS (4 tests)

- [ ] **Step 6: Commit**

```bash
git add apps/api/scripts/export_data.py apps/api/tests/test_export_data.py .gitignore
git commit -m "feat: add export_data.py to dump companies/orgs/reviews to JSONL"
```

---

### Task 2: `import_data.py` — upsert JSONL files into the target DB

**Files:**
- Create: `apps/api/scripts/import_data.py`
- Test: `apps/api/tests/test_import_data.py`

**Interfaces:**
- Consumes: `COMPANY_FIELDS`, `ORGANIZATION_FIELDS`, `REVIEW_FIELDS` field-name lists (same names as Task 1, used only to validate row completeness in tests — `import_data.py` itself reads whatever keys are present in each JSON object via explicit per-entity kwargs builders, see below).
- Produces:
  - `read_jsonl(path: Path) -> list[dict]`
  - `upsert_rows(db: Session, model, rows: list[dict], kwargs_fn) -> tuple[int, int]` — returns `(inserted, updated)`.
  - `import_all(db: Session, data_dir: Path, dry_run: bool = False) -> dict[str, tuple[int, int]]` — keys `"companies"`, `"organizations"`, `"reviews"`, each `(inserted, updated)`.

- [ ] **Step 1: Write the failing tests**

Create `apps/api/tests/test_import_data.py`:

```python
from datetime import date

from app.models.company import Company
from app.models.enums import OrganizationScrapeStatus, ReviewStatus, ScrapeMode
from app.models.organization import Organization
from app.models.review import Review
from scripts.export_data import export_companies, export_organizations, export_reviews
from scripts.import_data import import_all


def _seed_source(db_session):
    """Populate db_session as if it were the source server, return (company, org, review)."""
    company = Company(name="Acme")
    db_session.add(company)
    db_session.commit()

    org = Organization(
        name="Point 1",
        yandex_url="https://yandex.ru/maps/org/x/1/",
        normalized_url="https://yandex.ru/maps/org/x/1",
        company_id=company.id,
        preferred_scrape_mode=ScrapeMode.public,
        yandex_scrape_status=OrganizationScrapeStatus.success,
    )
    db_session.add(org)
    db_session.commit()

    review = Review(
        organization_id=org.id,
        scrape_mode=ScrapeMode.public,
        rating=5,
        review_text="Great",
        content_hash="hash1",
        review_date=date(2026, 1, 1),
        status=ReviewStatus.new,
    )
    db_session.add(review)
    db_session.commit()
    return company, org, review


def _export_all(db_session, out_dir):
    export_companies(db_session, out_dir / "companies.jsonl")
    export_organizations(db_session, out_dir / "organizations.jsonl")
    export_reviews(db_session, out_dir / "reviews.jsonl")


def test_import_into_empty_db_reproduces_source_rows(db_session, target_db_session, tmp_path):
    company, org, review = _seed_source(db_session)
    _export_all(db_session, tmp_path)

    summary = import_all(target_db_session, tmp_path)

    assert summary == {"companies": (1, 0), "organizations": (1, 0), "reviews": (1, 0)}
    imported_org = target_db_session.query(Organization).filter(Organization.id == org.id).one()
    assert imported_org.name == "Point 1"
    assert imported_org.company_id == company.id
    imported_review = target_db_session.query(Review).filter(Review.id == review.id).one()
    assert imported_review.review_text == "Great"
    assert imported_review.status == ReviewStatus.new
    assert imported_review.paid_marked_by_user_id is None
    assert imported_review.replied_by_user_id is None


def test_reimport_updates_changed_fields_without_duplicating(db_session, target_db_session, tmp_path):
    company, org, review = _seed_source(db_session)
    _export_all(db_session, tmp_path)
    import_all(target_db_session, tmp_path)

    # Source-side edit, re-export, re-import.
    review.status = ReviewStatus.answered
    review.reply_text = "Thanks!"
    db_session.commit()
    _export_all(db_session, tmp_path)

    summary = import_all(target_db_session, tmp_path)

    assert summary == {"companies": (0, 1), "organizations": (0, 1), "reviews": (0, 1)}
    assert target_db_session.query(Review).count() == 1
    imported_review = target_db_session.query(Review).filter(Review.id == review.id).one()
    assert imported_review.status == ReviewStatus.answered
    assert imported_review.reply_text == "Thanks!"


def test_dry_run_does_not_commit(db_session, target_db_session, tmp_path):
    _seed_source(db_session)
    _export_all(db_session, tmp_path)

    summary = import_all(target_db_session, tmp_path, dry_run=True)

    assert summary == {"companies": (1, 0), "organizations": (1, 0), "reviews": (1, 0)}
    target_db_session.rollback()
    assert target_db_session.query(Company).count() == 0


def test_import_order_is_fk_safe_organizations_before_reviews_reference_company(
    db_session, target_db_session, tmp_path
):
    """organizations.jsonl references a company_id only defined in companies.jsonl;
    reviews.jsonl references an organization_id only defined in organizations.jsonl.
    Importing companies -> organizations -> reviews in that order must not FK-fail."""
    _seed_source(db_session)
    _export_all(db_session, tmp_path)

    summary = import_all(target_db_session, tmp_path)

    assert all(inserted == 1 for inserted, _ in summary.values())
```

Add a second SQLite session fixture to `apps/api/tests/conftest.py` representing the target server's independent database (the source `db_session` fixture already exists):

```python
@pytest.fixture()
def target_db_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd apps/api && pytest tests/test_import_data.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.import_data'` (and `fixture 'target_db_session' not found` until the conftest edit lands — add both before running)

- [ ] **Step 3: Add the `target_db_session` fixture**

Edit `apps/api/tests/conftest.py`, immediately after the existing `db_session` fixture, insert the fixture shown in Step 1 verbatim.

- [ ] **Step 4: Implement `apps/api/scripts/import_data.py`**

```python
"""Import companies + organizations + reviews from JSONL exports (see export_data.py)
into the target database, upserting by `id`. Idempotent -- safe to rerun against an
updated export to sync a target server with the source.

paid_marked_by_user_id / replied_by_user_id are never set here: export_data.py does
not include them (see its module docstring for why).
"""

from __future__ import annotations

import argparse
import json
from datetime import date, datetime
from pathlib import Path
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.company import Company
from app.models.enums import OrganizationScrapeStatus, ReviewPlatform, ReviewStatus, ScrapeMode
from app.models.organization import Organization
from app.models.review import Review

CHUNK_SIZE = 1000


def _parse_uuid(value: str | None) -> UUID | None:
    return UUID(value) if value is not None else None


def _parse_datetime(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value is not None else None


def _parse_date(value: str | None) -> date | None:
    return date.fromisoformat(value) if value is not None else None


def _company_kwargs(row: dict) -> dict:
    return {
        "id": _parse_uuid(row["id"]),
        "name": row["name"],
        "is_active": row["is_active"],
        "created_at": _parse_datetime(row["created_at"]),
        "updated_at": _parse_datetime(row["updated_at"]),
    }


def _organization_kwargs(row: dict) -> dict:
    return {
        "id": _parse_uuid(row["id"]),
        "name": row["name"],
        "yandex_url": row["yandex_url"],
        "normalized_url": row["normalized_url"],
        "external_id": row["external_id"],
        "address": row["address"],
        "rating": row["rating"],
        "review_count": row["review_count"],
        "yandex_rating_count": row["yandex_rating_count"],
        "gis2_url": row["gis2_url"],
        "gis2_rating": row["gis2_rating"],
        "gis2_review_count": row["gis2_review_count"],
        "gis2_rating_count": row["gis2_rating_count"],
        "google_url": row["google_url"],
        "google_rating": row["google_rating"],
        "google_review_count": row["google_review_count"],
        "google_rating_count": row["google_rating_count"],
        "preferred_scrape_mode": ScrapeMode(row["preferred_scrape_mode"]),
        "yandex_scrape_status": OrganizationScrapeStatus(row["yandex_scrape_status"]),
        "gis2_scrape_status": OrganizationScrapeStatus(row["gis2_scrape_status"]),
        "yandex_last_successful_scrape_at": _parse_datetime(row["yandex_last_successful_scrape_at"]),
        "gis2_last_successful_scrape_at": _parse_datetime(row["gis2_last_successful_scrape_at"]),
        "city": row["city"],
        "region": row["region"],
        "is_franchise": row["is_franchise"],
        "company_id": _parse_uuid(row["company_id"]),
        "created_at": _parse_datetime(row["created_at"]),
        "updated_at": _parse_datetime(row["updated_at"]),
    }


def _review_kwargs(row: dict) -> dict:
    return {
        "id": _parse_uuid(row["id"]),
        "organization_id": _parse_uuid(row["organization_id"]),
        "source": row["source"],
        "scrape_mode": ScrapeMode(row["scrape_mode"]),
        "external_review_id": row["external_review_id"],
        "author_name": row["author_name"],
        "rating": row["rating"],
        "review_text": row["review_text"],
        "review_date_text": row["review_date_text"],
        "review_date": _parse_date(row["review_date"]),
        "response_text": row["response_text"],
        "response_first_seen_at": _parse_datetime(row["response_first_seen_at"]),
        "content_hash": row["content_hash"],
        "first_seen_at": _parse_datetime(row["first_seen_at"]),
        "last_seen_at": _parse_datetime(row["last_seen_at"]),
        "status": ReviewStatus(row["status"]) if row["status"] is not None else None,
        "is_paid": row["is_paid"],
        "platform": ReviewPlatform(row["platform"]) if row["platform"] is not None else None,
        "paid_cost": row["paid_cost"],
        "reply_text": row["reply_text"],
        "reply_at": _parse_datetime(row["reply_at"]),
        "sentiment": row["sentiment"],
        "sentiment_score": row["sentiment_score"],
        "sentiment_confidence": row["sentiment_confidence"],
        "rating_sentiment_mismatch": row["rating_sentiment_mismatch"],
        "problems": row["problems"],
        "analyzed_at": _parse_datetime(row["analyzed_at"]),
    }


def read_jsonl(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _chunks(seq: list, size: int):
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


def upsert_rows(db: Session, model, rows: list[dict], kwargs_fn) -> tuple[int, int]:
    """Upsert `rows` into `model` by primary key `id`. Returns (inserted, updated)."""
    inserted = 0
    updated = 0

    ids = [_parse_uuid(row["id"]) for row in rows]
    existing_ids: set = set()
    for chunk in _chunks(ids, CHUNK_SIZE):
        found = db.query(model.id).filter(model.id.in_(chunk)).all()
        existing_ids.update(row[0] for row in found)

    for row in rows:
        kwargs = kwargs_fn(row)
        row_id = kwargs["id"]
        if row_id in existing_ids:
            update_kwargs = {k: v for k, v in kwargs.items() if k != "id"}
            db.query(model).filter(model.id == row_id).update(update_kwargs, synchronize_session=False)
            updated += 1
            continue
        try:
            with db.begin_nested():
                db.add(model(**kwargs))
        except IntegrityError:
            update_kwargs = {k: v for k, v in kwargs.items() if k != "id"}
            db.query(model).filter(model.id == row_id).update(update_kwargs, synchronize_session=False)
            updated += 1
        else:
            inserted += 1
            existing_ids.add(row_id)

    return inserted, updated


def import_all(db: Session, data_dir: Path, dry_run: bool = False) -> dict[str, tuple[int, int]]:
    summary = {
        "companies": upsert_rows(db, Company, read_jsonl(data_dir / "companies.jsonl"), _company_kwargs),
        "organizations": upsert_rows(
            db, Organization, read_jsonl(data_dir / "organizations.jsonl"), _organization_kwargs
        ),
        "reviews": upsert_rows(db, Review, read_jsonl(data_dir / "reviews.jsonl"), _review_kwargs),
    }
    if dry_run:
        db.rollback()
    else:
        db.commit()
    return summary


def _print_summary(summary: dict[str, tuple[int, int]], dry_run: bool) -> None:
    mode = "DRY RUN (nothing written)" if dry_run else "committed"
    print(f"Import {mode}:")
    for name, (inserted, updated) in summary.items():
        print(f"  {name}: {inserted} inserted, {updated} updated")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Import companies/organizations/reviews from JSONL exports (see export_data.py)."
    )
    parser.add_argument(
        "--dir", type=Path, default=Path("data_export"),
        help="Directory containing companies.jsonl / organizations.jsonl / reviews.jsonl",
    )
    parser.add_argument("--dry-run", action="store_true", help="Parse and report without writing to the DB")
    args = parser.parse_args(argv)

    from app.core.database import SessionLocal

    db = SessionLocal()
    try:
        summary = import_all(db, args.dir, dry_run=args.dry_run)
    finally:
        db.close()
    _print_summary(summary, args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd apps/api && pytest tests/test_import_data.py -v`
Expected: PASS (4 tests)

- [ ] **Step 6: Run the full existing suite to confirm no regressions**

Run: `cd apps/api && pytest -v`
Expected: PASS (all prior tests + the 8 new ones)

- [ ] **Step 7: Commit**

```bash
git add apps/api/scripts/import_data.py apps/api/tests/test_import_data.py apps/api/tests/conftest.py
git commit -m "feat: add import_data.py to upsert JSONL exports by id"
```

---

## Manual verification (not automated — run once against a real DB before relying on this for a production sync)

1. `cd apps/api && python -m scripts.export_data --out-dir data_export` against the dev DB (602 orgs / 52,620 reviews per the spec's snapshot) — confirm it completes and the three files' line counts match `SELECT count(*)` for each table.
2. `python -m scripts.import_data --dir data_export --dry-run` against the same DB — confirm the summary reports `(0 inserted, N updated)` for every table (everything already present, nothing changes).
3. Point `DATABASE_URL` at a scratch/empty database, run `alembic upgrade head` there, then `python -m scripts.import_data --dir data_export` — confirm row counts match the source and the web app renders organizations/reviews correctly against it.
