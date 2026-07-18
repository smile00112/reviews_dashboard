"""Bulk metrics-only scraper: refresh org rating + review_count from platform links.

Follows each organization's platform URL and writes the freshly scraped rating and
review count back onto the row. Metrics only — individual reviews are ignored.

  * Yandex  -> org.yandex_url -> rating, review_count
  * 2GIS    -> org.gis2_url   -> gis2_rating, gis2_review_count

Standalone operator job, deliberately separate from the /scrape API (which always
feeds yandex_url and writes the Yandex columns regardless of mode). Reuses the
existing scrapers unchanged, reading only ScrapeResult.organization.

Usage:
    python -m scripts.scrape_metrics [--platform {yandex,2gis,both}] [--limit N]
                                     [--only-missing] [--dry-run] [--log-file PATH]
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from app.models.organization import Organization
from app.services.metrics_service import (
    PLATFORM_COLUMNS as PLATFORMS,
    MetricsOutcome,
    MetricsService,
    Scrapers,
)


class RunLogger:
    """Mirror progress to stdout and, optionally, an append-only monitor file.

    Every line is timestamped and flushed immediately so an operator can
    `tail -f` the file while a long bulk run is in flight.
    """

    def __init__(self, path: Path | None) -> None:
        self.path = path
        self._fh = None
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            self._fh = path.open("a", encoding="utf-8")

    def log(self, msg: str, *, stamp: bool = True) -> None:
        print(msg)
        if self._fh is not None:
            line = f"{datetime.now(timezone.utc).isoformat(timespec='seconds')} {msg}" if stamp else msg
            self._fh.write(line + "\n")
            self._fh.flush()

    def close(self) -> None:
        if self._fh is not None:
            self._fh.close()
            self._fh = None


@dataclass
class PlatformSummary:
    updated: int = 0
    failed: int = 0
    manual_action: int = 0
    skipped: int = 0


@dataclass
class RunSummary:
    per_platform: dict[str, PlatformSummary] = field(default_factory=dict)

    def get(self, platform: str) -> PlatformSummary:
        return self.per_platform.setdefault(platform, PlatformSummary())


def select_orgs(session, limit: int | None, offset: int = 0) -> list[Organization]:
    # created_at ties on bulk-imported rows; id breaks them so "first N" is stable.
    query = session.query(Organization).order_by(Organization.created_at, Organization.id)
    if offset:
        query = query.offset(offset)
    if limit is not None:
        query = query.limit(limit)
    return query.all()


def run(
    session,
    scrapers: Scrapers,
    platforms: list[str],
    limit: int | None,
    only_missing: bool,
    dry_run: bool,
    offset: int = 0,
    logger: RunLogger | None = None,
) -> RunSummary:
    logger = logger or RunLogger(None)
    summary = RunSummary()
    service = MetricsService(session, scrapers=scrapers)
    orgs = select_orgs(session, limit, offset)
    logger.log(f"start platforms={','.join(platforms)} orgs={len(orgs)} offset={offset} dry_run={dry_run}")
    for idx, org in enumerate(orgs, start=1):
        label = org.name or str(org.id)
        for platform in platforms:
            url_attr, rating_col = PLATFORMS[platform][0], PLATFORMS[platform][1]
            psummary = summary.get(platform)
            url = getattr(org, url_attr)
            if not url:
                psummary.skipped += 1
                logger.log(f"  [{idx}/{len(orgs)}] [{platform}] {label}: skip (no url)")
                continue
            if only_missing and getattr(org, rating_col) is not None:
                psummary.skipped += 1
                logger.log(f"  [{idx}/{len(orgs)}] [{platform}] {label}: skip (already has value)")
                continue
            result = service.refresh_organization(org, platform)
            outcome = result.outcome.value if result.outcome is not MetricsOutcome.manual_action else "manual_action"
            if result.outcome is MetricsOutcome.updated:
                psummary.updated += 1
                detail = (
                    f" rating={result.payload['rating_after']}"
                    f" rating_count={result.payload['rating_count_after']}"
                    f" review_count={result.payload['review_count_after']}"
                )
            elif result.outcome is MetricsOutcome.manual_action:
                psummary.manual_action += 1
                detail = f" ({result.error_code or 'no rating'})"
            else:
                psummary.failed += 1
                detail = f" ({result.error_code or 'no rating'})"
            logger.log(f"  [{idx}/{len(orgs)}] [{platform}] {label}: {outcome}{detail}")
        if not dry_run:
            session.commit()
    if dry_run:
        session.rollback()
    return summary


def _print_summary(summary: RunSummary, dry_run: bool, logger: RunLogger) -> None:
    mode = "DRY RUN (nothing written)" if dry_run else "committed"
    logger.log(f"\nScrape metrics {mode}:", stamp=False)
    for platform, ps in summary.per_platform.items():
        logger.log(
            f"  {platform}: updated={ps.updated} failed={ps.failed} "
            f"manual_action={ps.manual_action} skipped={ps.skipped}"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Refresh org rating/review_count from platform links.")
    parser.add_argument("--platform", choices=["yandex", "2gis", "both"], default="both")
    parser.add_argument("--limit", type=int, default=None, help="Max organizations to process")
    parser.add_argument("--offset", type=int, default=0, help="Skip the first N organizations")
    parser.add_argument("--only-missing", action="store_true", help="Skip orgs that already have the metric")
    parser.add_argument("--dry-run", action="store_true", help="Scrape and report without writing to the DB")
    parser.add_argument(
        "--log-file",
        nargs="?",
        const="__auto__",
        default=None,
        help="Also write timestamped progress to a monitor file. Bare flag = logs/scrape_metrics_<ts>.log",
    )
    args = parser.parse_args(argv)

    platforms = ["yandex", "2gis"] if args.platform == "both" else [args.platform]

    log_path: Path | None = None
    if args.log_file == "__auto__":
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        log_path = Path("logs") / f"scrape_metrics_{ts}.log"
    elif args.log_file:
        log_path = Path(args.log_file)

    from app.core.database import SessionLocal

    logger = RunLogger(log_path)
    if log_path is not None:
        print(f"Logging to {log_path.resolve()}", file=sys.stderr)

    scrapers = Scrapers()
    session = SessionLocal()
    try:
        summary = run(
            session,
            scrapers,
            platforms,
            limit=args.limit,
            only_missing=args.only_missing,
            dry_run=args.dry_run,
            offset=args.offset,
            logger=logger,
        )
    finally:
        session.close()
    _print_summary(summary, args.dry_run, logger)
    logger.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
