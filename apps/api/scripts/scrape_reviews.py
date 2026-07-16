"""Bulk review collector: collect an organization's reviews from a platform link.

Unlike ``scripts.scrape_metrics`` (which refreshes rating/review_count only), this
collects the individual reviews and persists them through ``ScrapeService`` — so it
inherits, rather than reimplements, the dedup contract, the organization info refresh
(name/rating/review_count/rating_count/address), the daily rating snapshot, and the
``ScrapeRun`` audit row every attempt must produce.

By default the scrapers stop at ``http_scrape_limit`` (150) reviews. ``--all-reviews``
lifts that cap for orgs with more (e.g. 1110 on a single Yandex org).

Usage:
    python -m scripts.scrape_reviews --org-id <uuid> [options]
    python -m scripts.scrape_reviews --all [options]

Options:
    --platform {yandex,2gis}   which platform's link to follow (default: yandex)
    --mode {...}               override the platform's default scrape mode
    --all-reviews              collect everything, ignoring the settings cap
    --limit N / --offset N     how many ORGANIZATIONS to process (not reviews)
    --dry-run                  print the plan (orgs + mode + URL); scrape nothing
    --log-file [PATH]          also write timestamped progress to a file

Note on --dry-run: it previews rather than scraping-then-rolling-back (the shape
scripts.scrape_metrics uses). ScrapeService commits its own writes, so there is
nothing left for this script to roll back once a scrape has run.
"""

from __future__ import annotations

import argparse
import math
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from app.models.enums import ScrapeMode
from app.models.organization import Organization
from app.services.scrape_service import ScrapeService, _mode_url
from scripts.scrape_metrics import RunLogger

# Which modes belong to which platform, and which mode a platform picks by default.
# yandex → public_http: it is the only Yandex mode that can route through the proxy
# pool (Chromium cannot authenticate against the SOCKS5 pool), and Yandex rate-limits
# a datacenter IP with HTTP 429 well before a full collection finishes.
PLATFORM_MODES: dict[str, tuple[ScrapeMode, ...]] = {
    "yandex": (ScrapeMode.public_http, ScrapeMode.public, ScrapeMode.operator_auth, ScrapeMode.scrapeops),
    "2gis": (ScrapeMode.twogis_api,),
}
PLATFORM_DEFAULT_MODE: dict[str, ScrapeMode] = {
    "yandex": ScrapeMode.public_http,
    "2gis": ScrapeMode.twogis_api,
}

# Modes that scroll a live page instead of paginating: they have no limit/max_pages
# knob, so --all-reviews cannot be honoured and must not be silently ignored.
SCROLL_MODES = (ScrapeMode.public, ScrapeMode.operator_auth)

# Runaway guard for --all-reviews. Pagination already stops when a page yields no new
# reviews; at ~50 reviews/page this covers ~5000, well above the largest known org.
ALL_REVIEWS_MAX_PAGES = 100


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Collect organization reviews from a platform link.")
    parser.add_argument("--org-id", default=None, help="Scrape a single organization by UUID")
    parser.add_argument("--all", action="store_true", help="Scrape every organization")
    parser.add_argument("--platform", choices=sorted(PLATFORM_MODES), default="yandex")
    parser.add_argument(
        "--mode",
        choices=[m.value for m in ScrapeMode],
        default=None,
        help="Override the platform's default scrape mode",
    )
    parser.add_argument(
        "--all-reviews",
        action="store_true",
        help="Collect every review, ignoring the configured cap (default: settings values)",
    )
    parser.add_argument("--limit", type=int, default=None, help="Max ORGANIZATIONS to process")
    parser.add_argument("--offset", type=int, default=0, help="Skip the first N organizations")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print which orgs would be scraped, with mode and URL. Scrapes nothing, writes nothing.",
    )
    parser.add_argument(
        "--log-file",
        nargs="?",
        const="__auto__",
        default=None,
        help="Also write timestamped progress to a monitor file. Bare flag = logs/scrape_reviews_<ts>.log",
    )
    return parser


def resolve_mode(args) -> ScrapeMode:
    if args.mode:
        return ScrapeMode(args.mode)
    return PLATFORM_DEFAULT_MODE[args.platform]


def resolve_overrides(args) -> dict:
    """Scraper caps for this run. Empty = the scrapers' settings values."""
    if not args.all_reviews:
        return {}
    return {"limit": math.inf, "max_pages": ALL_REVIEWS_MAX_PAGES}


def validate_args(args) -> None:
    """Reject incoherent flag combinations before any scraping starts."""
    parser = build_parser()
    if bool(args.org_id) == bool(args.all):
        parser.error("exactly one of --org-id or --all is required")

    if args.mode:
        mode = ScrapeMode(args.mode)
        if mode not in PLATFORM_MODES[args.platform]:
            parser.error(
                f"--mode {mode.value} does not belong to --platform {args.platform} "
                f"(valid: {', '.join(m.value for m in PLATFORM_MODES[args.platform])})"
            )

    if args.all_reviews and resolve_mode(args) in SCROLL_MODES:
        parser.error(
            f"--all-reviews is not supported for mode {resolve_mode(args).value}: it scrolls a live "
            "page and has no review cap to lift. Use --mode public_http."
        )

    if args.org_id:
        try:
            UUID(args.org_id)
        except ValueError:
            parser.error(f"--org-id is not a valid UUID: {args.org_id}")


@dataclass
class Summary:
    success: int = 0
    failed: int = 0
    manual_action: int = 0
    skipped: int = 0
    reviews_inserted: int = 0
    reviews_updated: int = 0
    planned: int = 0  # --dry-run only: orgs that would be scraped


def select_orgs(session, args) -> list[Organization]:
    if args.org_id:
        org = session.query(Organization).filter(Organization.id == UUID(args.org_id)).first()
        return [org] if org else []
    # created_at ties on bulk-imported rows; id breaks them so "first N" is stable
    # (same ordering as scripts.scrape_metrics).
    query = session.query(Organization).order_by(Organization.created_at, Organization.id)
    if args.offset:
        query = query.offset(args.offset)
    if args.limit is not None:
        query = query.limit(args.limit)
    return query.all()


def run(session, args, logger: RunLogger) -> Summary:
    mode = resolve_mode(args)
    overrides = resolve_overrides(args)
    summary = Summary()
    orgs = select_orgs(session, args)

    cap = "all" if args.all_reviews else "settings"
    logger.log(
        f"start platform={args.platform} mode={mode.value} orgs={len(orgs)} "
        f"reviews={cap} dry_run={args.dry_run}"
    )

    service = ScrapeService(session)
    for idx, org in enumerate(orgs, start=1):
        label = org.name or str(org.id)
        url = _mode_url(org, mode)
        if not url:
            summary.skipped += 1
            logger.log(f"  [{idx}/{len(orgs)}] {label}: skip (no {args.platform} url)")
            continue

        if args.dry_run:
            # A scrape-then-rollback dry run is not possible here: ScrapeService
            # commits its own writes, so by the time this function could roll back,
            # the reviews are already persisted. Preview the plan instead of lying.
            summary.planned += 1
            logger.log(f"  [{idx}/{len(orgs)}] {label}: would scrape {mode.value} {url}")
            continue

        run_row = service.create_run(org.id, mode)
        service.execute_run(run_row.id, **overrides)
        run_row = service.get_run(run_row.id)

        status = run_row.status.value
        if status == "success":
            summary.success += 1
            summary.reviews_inserted += run_row.reviews_inserted or 0
            summary.reviews_updated += run_row.reviews_updated or 0
            detail = (
                f" seen={run_row.reviews_seen} inserted={run_row.reviews_inserted}"
                f" updated={run_row.reviews_updated}"
            )
        else:
            if status == "needs_manual_action":
                summary.manual_action += 1
            else:
                summary.failed += 1
            detail = f" ({run_row.error_code}: {run_row.error_message})"
        logger.log(f"  [{idx}/{len(orgs)}] {label}: {status}{detail}")

    return summary


def _print_summary(summary: Summary, dry_run: bool, logger: RunLogger) -> None:
    if dry_run:
        logger.log("\nScrape reviews DRY RUN (nothing scraped, nothing written):", stamp=False)
        logger.log(f"  would scrape={summary.planned} skipped={summary.skipped}")
        return
    logger.log("\nScrape reviews committed:", stamp=False)
    logger.log(
        f"  success={summary.success} failed={summary.failed} "
        f"manual_action={summary.manual_action} skipped={summary.skipped}"
    )
    logger.log(f"  reviews inserted={summary.reviews_inserted} updated={summary.reviews_updated}")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    validate_args(args)

    log_path: Path | None = None
    if args.log_file == "__auto__":
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        log_path = Path("logs") / f"scrape_reviews_{ts}.log"
    elif args.log_file:
        log_path = Path(args.log_file)

    from app.core.database import SessionLocal

    logger = RunLogger(log_path)
    if log_path is not None:
        print(f"Logging to {log_path.resolve()}", file=sys.stderr)

    session = SessionLocal()
    try:
        summary = run(session, args, logger)
    finally:
        session.close()
    _print_summary(summary, args.dry_run, logger)
    logger.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
