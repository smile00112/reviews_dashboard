"""Import companies + organization branches from companies_data.csv.

Pure parsing helpers live here alongside the DB upsert layer and CLI. Reuses
app.services.url_utils for all Yandex URL handling. Idempotent: re-running
updates existing rows instead of inserting duplicates.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass

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
