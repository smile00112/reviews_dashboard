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
                                     [--only-missing] [--dry-run]
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field

from app.models.enums import OrganizationScrapeStatus
from app.models.organization import Organization
from app.scraper.twogis_api import TwogisApiScraper
from app.scraper.types import ScrapeResult
from app.scraper.yandex_http import YandexHttpScraper
from app.scraper.yandex_scrapeops import YandexScrapeOpsScraper

# platform -> (url attribute, rating column, review_count column, rating_count column)
PLATFORMS = {
    "yandex": ("yandex_url", "rating", "review_count", "yandex_rating_count"),
    "2gis": ("gis2_url", "gis2_rating", "gis2_review_count", "gis2_rating_count"),
}


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


class Scrapers:
    """Lazily-constructed scraper instances shared across the run."""

    def __init__(self) -> None:
        self.yandex_http = YandexHttpScraper()
        self.yandex_proxy = YandexScrapeOpsScraper()
        self.twogis = TwogisApiScraper()

    def scrape(self, platform: str, url: str) -> ScrapeResult:
        if platform == "2gis":
            return self.twogis.scrape(url, metrics_only=True)
        # yandex: browserless first, ScrapeOps proxy fallback on failure/challenge
        # or when the page yielded no rating.
        result = self.yandex_http.scrape(url, metrics_only=True)
        if result.needs_manual_action or result.error_code or result.organization.rating is None:
            fallback = self.yandex_proxy.scrape(url)
            if not (fallback.needs_manual_action or fallback.error_code) and fallback.organization.rating is not None:
                return fallback
        return result


def select_orgs(session, limit: int | None, offset: int = 0) -> list[Organization]:
    # created_at ties on bulk-imported rows; id breaks them so "first N" is stable.
    query = session.query(Organization).order_by(Organization.created_at, Organization.id)
    if offset:
        query = query.offset(offset)
    if limit is not None:
        query = query.limit(limit)
    return query.all()


def apply_result(
    org: Organization,
    platform: str,
    result: ScrapeResult,
    summary: PlatformSummary,
) -> str:
    """Write scraped metrics onto the org for one platform. Returns an outcome label.

    Never overwrites an existing value with null: a scrape that yields no rating is a
    failure, not a reason to wipe a known figure.
    """
    _, rating_col, count_col, rating_count_col = PLATFORMS[platform]
    if result.needs_manual_action:
        summary.manual_action += 1
        return "manual_action"
    if result.error_code or result.organization.rating is None:
        summary.failed += 1
        return "failed"

    from datetime import datetime, timezone

    setattr(org, rating_col, result.organization.rating)
    if result.organization.review_count is not None:
        setattr(org, count_col, result.organization.review_count)
    if result.organization.rating_count is not None:
        setattr(org, rating_count_col, result.organization.rating_count)
    org.last_scrape_status = OrganizationScrapeStatus.success
    org.last_successful_scrape_at = datetime.now(timezone.utc)
    summary.updated += 1
    return "updated"


def run(
    session,
    scrapers: Scrapers,
    platforms: list[str],
    limit: int | None,
    only_missing: bool,
    dry_run: bool,
    offset: int = 0,
) -> RunSummary:
    summary = RunSummary()
    orgs = select_orgs(session, limit, offset)
    for org in orgs:
        label = org.name or str(org.id)
        for platform in platforms:
            url_attr, rating_col, _, _ = PLATFORMS[platform]
            psummary = summary.get(platform)
            url = getattr(org, url_attr)
            if not url:
                psummary.skipped += 1
                print(f"  [{platform}] {label}: skip (no url)")
                continue
            if only_missing and getattr(org, rating_col) is not None:
                psummary.skipped += 1
                print(f"  [{platform}] {label}: skip (already has value)")
                continue
            result = scrapers.scrape(platform, url)
            outcome = apply_result(org, platform, result, psummary)
            detail = ""
            if outcome == "updated":
                detail = f" rating={result.organization.rating} count={result.organization.review_count}"
            elif outcome in ("failed", "manual_action"):
                detail = f" ({result.error_code or 'no rating'})"
            print(f"  [{platform}] {label}: {outcome}{detail}")
        if not dry_run:
            session.commit()
    if dry_run:
        session.rollback()
    return summary


def _print_summary(summary: RunSummary, dry_run: bool) -> None:
    mode = "DRY RUN (nothing written)" if dry_run else "committed"
    print(f"\nScrape metrics {mode}:")
    for platform, ps in summary.per_platform.items():
        print(
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
    args = parser.parse_args(argv)

    platforms = ["yandex", "2gis"] if args.platform == "both" else [args.platform]

    from app.core.database import SessionLocal

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
        )
    finally:
        session.close()
    _print_summary(summary, args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
