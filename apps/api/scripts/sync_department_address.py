"""Sync the CSV `Department` column into Organization.address.

The ratings CSV carries one Department label per branch plus several monthly
snapshot columns of Yandex / 2GIS links. Organization.name is unusable as a key
(the scraper overwrites it with the platform's own title), so matching goes
strictly by URL: any Yandex link in the row, normalized and looked up against
`normalized_url`; failing that, any 2GIS link matched against `gis2_url`.

Never inserts or renames — only fills `address`. Unmatched rows and rows that
would give one organization two different Departments are reported. Idempotent.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass, field

from app.models.organization import Organization
from app.services.url_utils import normalize_yandex_url

# Same layout as scripts/import_companies_csv.py.
HEADER_ROWS = 2
COL_REGION = 0
COL_DEPARTMENT = 2
COL_COMPANY = 3


@dataclass
class SyncSummary:
    updated: int = 0
    unchanged: int = 0
    unmatched: list[tuple[str, str, str]] = field(default_factory=list)  # (city, company, department)
    conflicts: list[tuple[str, str, str]] = field(default_factory=list)  # (org_name, url, departments)


def _cell(row: list[str], index: int) -> str:
    return row[index].strip() if len(row) > index else ""


def read_csv_rows(path: str) -> list[list[str]]:
    with open(path, encoding="utf-8", newline="") as handle:
        return list(csv.reader(handle))[HEADER_ROWS:]


def build_url_index(session) -> tuple[dict[str, Organization], dict[str, Organization]]:
    """Return (normalized Yandex URL -> org, 2GIS URL -> org)."""
    yandex: dict[str, Organization] = {}
    gis2: dict[str, Organization] = {}
    for org in session.query(Organization).all():
        if org.normalized_url:
            yandex.setdefault(org.normalized_url, org)
        if org.gis2_url:
            gis2.setdefault(org.gis2_url.strip(), org)
    return yandex, gis2


def find_org(
    row: list[str],
    yandex_index: dict[str, Organization],
    gis2_index: dict[str, Organization],
) -> Organization | None:
    for cell in row:
        url = cell.strip()
        if not url.startswith("http") or "yandex" not in url:
            continue
        try:
            normalized = normalize_yandex_url(url)
        except ValueError:
            continue
        org = yandex_index.get(normalized)
        if org is not None:
            return org
    for cell in row:
        url = cell.strip()
        if url.startswith("http") and "2gis" in url:
            org = gis2_index.get(url)
            if org is not None:
                return org
    return None


def sync_rows(session, rows: list[list[str]], dry_run: bool = False) -> SyncSummary:
    summary = SyncSummary()
    yandex_index, gis2_index = build_url_index(session)

    # Pass 1: collect every Department each organization is claimed by. The CSV
    # does contain branches sharing one short link, and picking either one would
    # write an address that is wrong half the time — those are left untouched.
    claims: dict[str, tuple[Organization, set[str]]] = {}
    for row in rows:
        department = _cell(row, COL_DEPARTMENT)
        if not department:
            continue
        org = find_org(row, yandex_index, gis2_index)
        if org is None:
            summary.unmatched.append((_cell(row, COL_REGION), _cell(row, COL_COMPANY), department))
            continue
        _, departments = claims.setdefault(str(org.id), (org, set()))
        departments.add(department)

    # Pass 2: write only the unambiguous ones.
    for org, departments in claims.values():
        if len(departments) > 1:
            summary.conflicts.append((org.name or str(org.id), org.yandex_url or "", " / ".join(sorted(departments))))
            continue
        department = next(iter(departments))
        if org.address == department:
            summary.unchanged += 1
            continue
        org.address = department
        summary.updated += 1

    if dry_run:
        session.rollback()
    else:
        session.commit()
    return summary


def _print_summary(summary: SyncSummary, dry_run: bool) -> None:
    mode = "DRY RUN (nothing written)" if dry_run else "committed"
    print(f"Department -> address sync {mode}:")
    print(f"  updated:   {summary.updated}")
    print(f"  unchanged: {summary.unchanged}")
    print(f"  unmatched: {len(summary.unmatched)}")
    for city, company, department in summary.unmatched:
        print(f"    - {city} | {company} | {department}")
    if summary.conflicts:
        print(f"  ambiguous (several Departments share one URL, address left as is): {len(summary.conflicts)}")
        for org_name, url, departments in summary.conflicts:
            print(f"    - {org_name} | {url} | {departments}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sync CSV Department column into Organization.address.")
    parser.add_argument("csv_path", help="Path to the ratings CSV")
    parser.add_argument("--dry-run", action="store_true", help="Report without writing to the DB")
    args = parser.parse_args(argv)

    from app.core.database import SessionLocal

    rows = read_csv_rows(args.csv_path)
    session = SessionLocal()
    try:
        summary = sync_rows(session, rows, dry_run=args.dry_run)
    finally:
        session.close()
    _print_summary(summary, args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
