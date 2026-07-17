"""Export reviews (with company responses) to CSV for a date range.

Reads directly via the app's SQLAlchemy session/config (SessionLocal), so it
picks up DATABASE_URL from .env like the rest of the API. Read-only: issues a
single SELECT joining reviews + organizations, writes a CSV, no DB writes.
"""

from __future__ import annotations

import argparse
import csv
import sys
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import select

from app.core.database import SessionLocal
from app.models.enums import ReviewPlatform
from app.models.organization import Organization
from app.models.review import Review

COLUMNS = [
    "organization",
    "address",
    "author_name",
    "rating",
    "review_date",
    "review_text",
    "response_text",
]


def parse_date(raw: str) -> date:
    return datetime.strptime(raw, "%Y-%m-%d").date()


def export_reviews(start: date, end: date, platform: ReviewPlatform, out_path: Path) -> int:
    stmt = (
        select(
            Organization.name,
            Organization.address,
            Review.author_name,
            Review.rating,
            Review.review_date,
            Review.review_text,
            Review.response_text,
        )
        .join(Organization, Organization.id == Review.organization_id)
        .where(
            Review.platform == platform,
            Review.review_date >= start,
            Review.review_date <= end,
        )
        .order_by(Organization.name, Review.review_date)
    )

    db = SessionLocal()
    try:
        rows = db.execute(stmt).all()
    finally:
        db.close()

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(COLUMNS)
        writer.writerows(rows)

    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", required=True, type=parse_date, help="YYYY-MM-DD, inclusive")
    parser.add_argument("--end", required=True, type=parse_date, help="YYYY-MM-DD, inclusive")
    parser.add_argument(
        "--platform",
        choices=[p.value for p in ReviewPlatform],
        default=ReviewPlatform.yandex.value,
    )
    parser.add_argument("--out", type=Path, default=None, help="Output CSV path (default: reports/<platform>_reviews_<start>_<end>.csv)")
    args = parser.parse_args()

    if args.end < args.start:
        print("--end must not be before --start", file=sys.stderr)
        raise SystemExit(1)

    out_path = args.out or Path("reports") / f"{args.platform}_reviews_{args.start}_{args.end}.csv"
    count = export_reviews(args.start, args.end, ReviewPlatform(args.platform), out_path)
    print(f"{count} reviews -> {out_path}")


if __name__ == "__main__":
    main()
