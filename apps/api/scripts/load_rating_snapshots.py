"""Load a collected Sprav rating history into rating_snapshot (platform=yandex).

Input is the JSON written by ``scripts.sprav_chain_ratings``. One snapshot row
per (organization, week).

``review_count`` stays NULL: the cabinet publishes a weekly *rating* but no
weekly review count, and a 0 there would be a real measurement rather than the
"нет данных" this actually is (feature 014 rule). The consequence is that the
volume trend on /ratings gains nothing from these rows — only the rating trend.

Idempotent — (organization_id, platform, captured_on) is unique, so re-running
updates changed ratings instead of duplicating rows.

    python -m scripts.load_rating_snapshots --in .local/sprav-chain-2082553.json --dry-run
    python -m scripts.load_rating_snapshots --in .local/sprav-chain-2082553.json --min-confidence 0.7
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path

from app.models.enums import ReviewPlatform
from app.models.rating_snapshot import RatingSnapshot


@dataclass
class LoadSummary:
    organizations: int = 0
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0
    skipped: dict[str, int] = field(default_factory=lambda: {
        "unmatched": 0, "low_confidence": 0, "no_history": 0, "no_rating": 0,
    })


def run(session, records: list[dict], *, min_confidence: float, dry_run: bool) -> LoadSummary:
    """Diff the records against what is already stored, then apply."""
    existing = {
        (str(row.organization_id), row.captured_on): row
        for row in session.query(RatingSnapshot).filter(RatingSnapshot.platform == ReviewPlatform.yandex)
    }
    now = datetime.now(timezone.utc)
    summary = LoadSummary()
    pending: list[dict] = []

    for record in records:
        org_id = record.get("org_id")
        if not org_id:
            summary.skipped["unmatched"] += 1
            continue
        # Only the address fallback needs vetting; an external_id match is exact.
        if record.get("match_method") == "address" and (record.get("match_confidence") or 0) < min_confidence:
            summary.skipped["low_confidence"] += 1
            continue
        history = record.get("history") or []
        if not history:
            summary.skipped["no_history"] += 1
            continue

        summary.organizations += 1
        for point in history:
            week, rating = point.get("week"), point.get("rating")
            if not week or rating is None:
                # A week the cabinet published no rating for is a gap, not a zero.
                summary.skipped["no_rating"] += 1
                continue
            captured_on = date.fromisoformat(week)
            row = existing.get((org_id, captured_on))
            if row is None:
                summary.inserted += 1
                pending.append(
                    {
                        # bulk_insert_mappings bypasses type coercion, and the
                        # SQLite UUID variant rejects a plain string.
                        "organization_id": uuid.UUID(org_id) if isinstance(org_id, str) else org_id,
                        "platform": ReviewPlatform.yandex,
                        "rating": rating,
                        "review_count": None,  # the cabinet gives no per-week count
                        "captured_on": captured_on,
                        "captured_at": now,
                    }
                )
            elif float(row.rating) != float(rating):
                summary.updated += 1
                if not dry_run:
                    row.rating = rating
                    row.captured_at = now
            else:
                summary.unchanged += 1

    if not dry_run:
        if pending:
            session.bulk_insert_mappings(RatingSnapshot, pending)
        session.commit()
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Load Sprav rating history into rating_snapshot.")
    parser.add_argument("--in", dest="source", required=True, help="JSON from scripts.sprav_chain_ratings.")
    parser.add_argument("--dry-run", action="store_true", help="Report the diff without writing.")
    parser.add_argument("--min-confidence", type=float, default=0.0,
                        help="Skip address-matched branches below this confidence.")
    args = parser.parse_args(argv)

    document = json.loads(Path(args.source).read_text(encoding="utf-8"))
    records = document.get("records") or []
    if not records:
        print("error: no records in the input document", file=sys.stderr)
        return 1

    from app.core.database import SessionLocal

    session = SessionLocal()
    try:
        summary = run(session, records, min_confidence=args.min_confidence, dry_run=args.dry_run)
    finally:
        session.close()

    print("DRY RUN (nothing written)" if args.dry_run else "committed")
    print(f"  organizations: {summary.organizations}")
    print(f"  inserted:      {summary.inserted}")
    print(f"  updated:       {summary.updated}")
    print(f"  unchanged:     {summary.unchanged}")
    for reason, count in summary.skipped.items():
        print(f"  skipped {reason}: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
