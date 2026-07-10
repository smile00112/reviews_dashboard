import pytest

from app.models.organization import Organization
from scripts.import_companies_csv import (
    RowData,
    parse_count,
    parse_rating,
    parse_row,
    select_yandex_url,
)


def test_organization_persists_with_null_urls(db_session):
    org = Organization(name="Сочи-04", city="Адлер", yandex_url=None, normalized_url=None)
    db_session.add(org)
    db_session.commit()
    db_session.refresh(org)
    assert org.id is not None
    assert org.yandex_url is None
    assert org.normalized_url is None


@pytest.mark.parametrize("raw,expected", [
    ("4,2", 4.2),
    ("5", 5.0),
    ("3.9", 3.9),
    ("-", None),
    ("-0", None),
    ("0", None),
    ("", None),
    ("  ", None),
])
def test_parse_rating(raw, expected):
    assert parse_rating(raw) == expected


@pytest.mark.parametrize("raw,expected", [
    ("18", 18),
    ("0", 0),
    ("", None),
    ("-", None),
    ("n/a", None),
])
def test_parse_count(raw, expected):
    assert parse_count(raw) == expected


def test_select_yandex_url_valid_canonical():
    url = "https://yandex.ru/maps/org/spoke/163787997704/"
    assert select_yandex_url(url) == url


def test_select_yandex_url_valid_shortlink():
    url = "https://yandex.by/maps/-/CPe4QI0P"
    assert select_yandex_url(url) == url


@pytest.mark.parametrize("raw", ["", "  ", "-", "https://go.2gis.com/Sf64K", "notaurl"])
def test_select_yandex_url_invalid_returns_none(raw):
    assert select_yandex_url(raw) is None


def test_parse_row_maps_columns():
    row = [""] * 16
    row[0] = "Адлер"
    row[2] = "Сочи-04 Адлер Ленина 73"
    row[3] = "SPOKE Россия"
    row[5] = "https://yandex.ru/maps/org/spoke/163787997704/"
    row[6] = "4,2"
    row[7] = "18"
    rd = parse_row(row)
    assert rd == RowData(
        company_name="SPOKE Россия",
        name="Сочи-04 Адлер Ленина 73",
        city="Адлер",
        yandex_url="https://yandex.ru/maps/org/spoke/163787997704/",
        rating=4.2,
        review_count=18,
    )


def test_parse_row_urlless_row():
    row = [""] * 16
    row[0] = "Москва"
    row[2] = "Точка-1"
    row[3] = "SPOKE Россия"
    rd = parse_row(row)
    assert rd is not None
    assert rd.yandex_url is None
    assert rd.rating is None
    assert rd.review_count is None


def test_parse_row_blank_or_no_company_returns_none():
    assert parse_row([""] * 16) is None
    row = [""] * 16
    row[2] = "Точка без компании"
    assert parse_row(row) is None
