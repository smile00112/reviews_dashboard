"""Import companies + organization branches from companies_data.csv.

Pure parsing helpers live here alongside the DB upsert layer and CLI. Reuses
app.services.url_utils for all Yandex URL handling. Idempotent: re-running
updates existing rows instead of inserting duplicates.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass

from app.models.company import Company
from app.models.enums import OrganizationScrapeStatus, ScrapeMode
from app.models.organization import Organization
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
