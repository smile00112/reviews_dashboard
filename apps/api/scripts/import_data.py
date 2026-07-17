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
