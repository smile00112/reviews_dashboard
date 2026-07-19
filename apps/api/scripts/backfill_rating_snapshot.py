"""Seed rating_snapshot from data already sitting on organizations.

rating_snapshot is normally written once per scrape run (ScrapeService calls
DashboardService.capture_snapshot after each scrape, feature 009). Organizations
scraped before that snapshot capture existed - or between deploys where no scrape
has run since - have no snapshot rows, so period-over-period rating deltas stay
None until their next scrape. This is a one-off backfill: it does not scrape
anything, it just writes today's (or --date's) snapshot from the rating/review_count
columns each organization already has from prior scrapes.

Usage:
    python -m scripts.backfill_rating_snapshot [--date YYYY-MM-DD] [--dry-run]
"""

from __future__ import annotations

import argparse
from datetime import date, datetime, timezone

from app.models.organization import Organization
from app.services.dashboard_service import DashboardService, _PLATFORM_COLS


def run(session, *, captured_on: date, dry_run: bool) -> dict[str, int]:
    # capture_snapshot commits per call - dry-run must skip calling it entirely,
    # not call-then-rollback, or it would write for real anyway.
    now = datetime.combine(captured_on, datetime.min.time(), tzinfo=timezone.utc)
    svc = DashboardService(session)
    summary = {"seeded": 0, "skipped": 0}
    orgs = session.query(Organization).order_by(Organization.created_at, Organization.id).all()
    for org in orgs:
        for platform, (rating_col, _count_col) in _PLATFORM_COLS.items():
            if getattr(org, rating_col) is None:
                summary["skipped"] += 1
                continue
            summary["seeded"] += 1
            if not dry_run:
                svc.capture_snapshot(org.id, platform, now=now)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Backfill rating_snapshot from existing organization data.")
    parser.add_argument("--date", type=date.fromisoformat, default=None, help="captured_on, default today (UTC)")
    parser.add_argument("--dry-run", action="store_true", help="Compute and report without writing to the DB")
    args = parser.parse_args(argv)

    captured_on = args.date or datetime.now(timezone.utc).date()

    from app.core.database import SessionLocal

    session = SessionLocal()
    try:
        summary = run(session, captured_on=captured_on, dry_run=args.dry_run)
    finally:
        session.close()

    mode = "DRY RUN (nothing written)" if args.dry_run else "committed"
    print(f"Backfill rating_snapshot for {captured_on} ({mode}): seeded={summary['seeded']} skipped={summary['skipped']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
