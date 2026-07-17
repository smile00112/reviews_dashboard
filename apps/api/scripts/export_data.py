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
