from datetime import date

import pytest

from app.scraper.normalize import normalize_review_date

TODAY = date(2026, 6, 30)


def test_iso_passthrough():
    assert normalize_review_date("2024-05-02") == date(2024, 5, 2)


def test_dotted_date():
    assert normalize_review_date("02.05.2024") == date(2024, 5, 2)


def test_full_russian_month():
    assert normalize_review_date("2 мая 2024") == date(2024, 5, 2)


def test_partial_russian_month_uses_current_year():
    assert normalize_review_date("2 мая", today=TODAY) == date(2026, 5, 2)


def test_english_month():
    assert normalize_review_date("2 May 2024") == date(2024, 5, 2)


@pytest.mark.parametrize(
    "text,expected",
    [
        ("сегодня", date(2026, 6, 30)),
        ("вчера", date(2026, 6, 29)),
        ("позавчера", date(2026, 6, 28)),
        ("5 дней назад", date(2026, 6, 25)),
        ("2 недели назад", date(2026, 6, 16)),
    ],
)
def test_relative_dates(text, expected):
    assert normalize_review_date(text, today=TODAY) == expected


@pytest.mark.parametrize("bad", [None, "", "   ", "белиберда", 123])
def test_unparseable_returns_none(bad):
    assert normalize_review_date(bad) is None  # type: ignore[arg-type]


def test_invalid_calendar_date_returns_none():
    assert normalize_review_date("32.13.2024") is None
