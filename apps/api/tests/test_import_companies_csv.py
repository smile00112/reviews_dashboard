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


from app.models.company import Company
from scripts.import_companies_csv import ImportSummary, import_rows


def _rows():
    return [
        RowData("SPOKE Россия", "Сочи-04", "Адлер",
                "https://yandex.ru/maps/org/spoke/163787997704/", 4.2, 18),
        RowData("SPOKE Россия", "Москва-1", "Москва", None, None, None),
        RowData("Мир Суши Россия", "Казань-3", "Казань",
                "https://yandex.by/maps/-/CPFFmP9O", 3.7, 51),
    ]


def test_import_creates_companies_and_orgs(db_session):
    summary = import_rows(db_session, _rows())
    assert summary.companies_created == 2
    assert summary.orgs_inserted == 3
    assert summary.orgs_without_url == 1
    assert db_session.query(Company).count() == 2
    assert db_session.query(Organization).count() == 3


def test_import_sets_normalized_url_and_external_id(db_session):
    import_rows(db_session, _rows())
    org = db_session.query(Organization).filter(Organization.name == "Сочи-04").one()
    assert org.normalized_url == "https://yandex.ru/maps/org/spoke/163787997704"
    assert org.external_id == "163787997704"
    assert org.company.name == "SPOKE Россия"
    assert float(org.rating) == 4.2
    assert org.review_count == 18


def test_import_is_idempotent(db_session):
    import_rows(db_session, _rows())
    summary = import_rows(db_session, _rows())
    assert summary.companies_created == 0
    assert summary.companies_found == 2
    assert summary.orgs_inserted == 0
    assert summary.orgs_updated == 3
    assert db_session.query(Company).count() == 2
    assert db_session.query(Organization).count() == 3


def test_import_urlless_dedup_by_company_name_city(db_session):
    import_rows(db_session, _rows())
    # Same URL-less branch again with a changed rating -> update, not insert.
    again = [RowData("SPOKE Россия", "Москва-1", "Москва", None, 4.5, 9)]
    import_rows(db_session, again)
    urlless = db_session.query(Organization).filter(Organization.normalized_url.is_(None)).all()
    assert len(urlless) == 1
    assert urlless[0].review_count == 9


def test_import_dry_run_writes_nothing(db_session):
    summary = import_rows(db_session, _rows(), dry_run=True)
    assert summary.orgs_inserted == 3
    assert db_session.query(Company).count() == 0
    assert db_session.query(Organization).count() == 0
