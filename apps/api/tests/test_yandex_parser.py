from datetime import date
from pathlib import Path

import pytest

from app.scraper.parser import is_owner_response, parse_reviews_from_html

FIXTURE = Path(__file__).parent / "fixtures" / "yandex_reviews_sample.html"


@pytest.fixture(scope="module")
def parsed():
    html = FIXTURE.read_text(encoding="utf-8")
    return parse_reviews_from_html(html)


def test_organization_metadata(parsed):
    org, _ = parsed
    assert org.name == "Кафе Пример"
    assert org.rating == 4.3
    assert org.review_count == 128


def test_owner_responses_excluded_from_guest_reviews(parsed):
    _, reviews = parsed
    # 3 guest reviews; the standalone owner-response block is dropped.
    assert len(reviews) == 3
    for r in reviews:
        assert not is_owner_response(r.review_text)


def test_rating_from_aria_label(parsed):
    _, reviews = parsed
    anna = next(r for r in reviews if r.author_name == "Анна Иванова")
    assert anna.rating == 4


def test_rating_from_full_star_count(parsed):
    _, reviews = parsed
    ivan = next(r for r in reviews if r.author_name == "Иван Петров")
    assert ivan.rating == 2


def test_date_normalized(parsed):
    _, reviews = parsed
    anna = next(r for r in reviews if r.author_name == "Анна Иванова")
    assert anna.review_date == date(2024, 5, 2)
    assert anna.review_date_text == "2 мая 2024"


def test_owner_response_attached_as_response_text(parsed):
    _, reviews = parsed
    maria = next(r for r in reviews if r.author_name == "Мария С.")
    assert maria.response_text and "Спасибо за отзыв" in maria.response_text


def test_empty_html_safe():
    org, reviews = parse_reviews_from_html("")
    assert reviews == []
    assert org.name is None
