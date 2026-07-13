"""Append a fresh rating/review-count column block to the operator's Google Sheet.

Matches sheet rows to organizations by their latest Yandex Maps link (the
rightmost non-empty "ЯК" column in each row, normalized via
app.services.url_utils.normalize_yandex_url), then appends 6 new columns at
the end of the sheet — rating + review count for Yandex, 2GIS and Google —
dated with today's date, sourced from the organizations table (rating /
yandex_rating_count / gis2_rating / gis2_rating_count / google_rating /
google_rating_count). Read-only against the DB; the sheet is the only thing
written.

Usage:
    python -m scripts.sync_ratings_to_sheet [--dry-run] [--credentials PATH]
                                             [--spreadsheet-id ID] [--gid GID]
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import datetime, timezone

import gspread

from app.core.config import settings
from app.models.organization import Organization
from app.services.url_utils import normalize_yandex_url

HEADER_ROW = 0  # column labels (0-indexed into get_all_values())
DATE_ROW = 1  # "на DD.MM.YY" block labels
DATA_START_ROW = 2  # first organization row

YANDEX_LINK_HEADER = "ЯК"

NEW_BLOCK_HEADERS = [
    "Рейтинг ЯК", "количество",
    "Рейтинг 2ГИС", "количество",
    "Рейтинг ГК", "количество",
]


@dataclass
class SyncSummary:
    matched: int = 0
    unmatched_orgs: list[str] = field(default_factory=list)
    duplicate_links: list[str] = field(default_factory=list)


def format_rating(value) -> str:
    if value is None:
        return ""
    text = f"{float(value):.2f}".rstrip("0").rstrip(".")
    return text.replace(".", ",")


def format_count(value) -> str:
    return "" if value is None else str(int(value))


def find_yandex_link_columns(header_row: list[str]) -> list[int]:
    return [i for i, cell in enumerate(header_row) if cell.strip() == YANDEX_LINK_HEADER]


def row_yandex_link(row: list[str], link_cols: list[int]) -> str | None:
    # Most recent block is rightmost; scan back-to-front for the latest usable link.
    for col in reversed(link_cols):
        if col < len(row):
            value = row[col].strip()
            if value and value != "-":
                return value
    return None


def build_org_index(session) -> dict[str, Organization]:
    """normalized yandex URL -> Organization, for orgs that have one."""
    index: dict[str, Organization] = {}
    orgs = session.query(Organization).filter(Organization.yandex_url.isnot(None)).all()
    for org in orgs:
        try:
            key = normalize_yandex_url(org.yandex_url)
        except Exception:
            continue
        index[key] = org
    return index


def build_new_block(
    all_values: list[list[str]],
    link_cols: list[int],
    org_by_url: dict[str, Organization],
) -> tuple[list[list[str]], SyncSummary]:
    summary = SyncSummary()
    seen_links: dict[str, int] = {}
    rows_out: list[list[str]] = []

    for row in all_values[DATA_START_ROW:]:
        link = row_yandex_link(row, link_cols)
        org = None
        if link:
            try:
                key = normalize_yandex_url(link)
            except Exception:
                key = None
            if key:
                if key in seen_links:
                    summary.duplicate_links.append(link)
                seen_links[key] = seen_links.get(key, 0) + 1
                org = org_by_url.get(key)

        if org is None:
            label = row[3] if len(row) > 3 and row[3] else (link or "(no link)")
            summary.unmatched_orgs.append(label)
            rows_out.append(["", "", "", "", "", ""])
            continue

        summary.matched += 1
        rows_out.append([
            format_rating(org.rating), format_count(org.yandex_rating_count),
            format_rating(org.gis2_rating), format_count(org.gis2_rating_count),
            format_rating(org.google_rating), format_count(org.google_rating_count),
        ])

    return rows_out, summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Append a dated rating/count block to the ratings Google Sheet.")
    parser.add_argument("--credentials", default=settings.google_sheets_credentials_path)
    parser.add_argument("--spreadsheet-id", default=settings.google_sheets_spreadsheet_id)
    parser.add_argument("--gid", type=int, default=settings.google_sheets_worksheet_gid)
    parser.add_argument("--dry-run", action="store_true", help="Compute the block and report, but don't write")
    args = parser.parse_args(argv)

    from app.core.database import SessionLocal

    gc = gspread.service_account(filename=args.credentials)
    sh = gc.open_by_key(args.spreadsheet_id)
    ws = sh.get_worksheet_by_id(args.gid)

    all_values = ws.get_all_values()
    link_cols = find_yandex_link_columns(all_values[HEADER_ROW])
    if not link_cols:
        print(f"No '{YANDEX_LINK_HEADER}' columns found in header row — nothing to match against.")
        return 1

    session = SessionLocal()
    try:
        org_by_url = build_org_index(session)
    finally:
        session.close()

    data_block, summary = build_new_block(all_values, link_cols, org_by_url)

    today = datetime.now(timezone.utc).strftime("%d.%m.%y")
    date_label = f"на {today}"

    print(f"Rows: {len(data_block)} | matched: {summary.matched} | unmatched: {len(summary.unmatched_orgs)}")
    if summary.duplicate_links:
        print(f"WARNING: {len(summary.duplicate_links)} Yandex links appear in more than one sheet row (each row gets the same org's data):")
        for link in summary.duplicate_links[:10]:
            print(f"  - {link}")
    if summary.unmatched_orgs:
        print(f"Unmatched rows (no org found for the row's Yandex link), first 20:")
        for label in summary.unmatched_orgs[:20]:
            print(f"  - {label}")

    if args.dry_run:
        print("\nDRY RUN — sheet not modified.")
        return 0

    start_col = ws.col_count + 1
    ws.add_cols(len(NEW_BLOCK_HEADERS))

    header_range = gspread.utils.rowcol_to_a1(HEADER_ROW + 1, start_col) + ":" + \
        gspread.utils.rowcol_to_a1(HEADER_ROW + 1, start_col + len(NEW_BLOCK_HEADERS) - 1)
    ws.update(range_name=header_range, values=[NEW_BLOCK_HEADERS], value_input_option="USER_ENTERED")

    date_cell = gspread.utils.rowcol_to_a1(DATE_ROW + 1, start_col)
    ws.update(range_name=date_cell, values=[[date_label]], value_input_option="USER_ENTERED")

    data_range = gspread.utils.rowcol_to_a1(DATA_START_ROW + 1, start_col) + ":" + \
        gspread.utils.rowcol_to_a1(DATA_START_ROW + len(data_block), start_col + len(NEW_BLOCK_HEADERS) - 1)
    ws.update(range_name=data_range, values=data_block, value_input_option="USER_ENTERED")

    print(f"\nWrote block '{date_label}' at columns {start_col}-{start_col + len(NEW_BLOCK_HEADERS) - 1}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
