"""Pure parsers for the Sprav chain pages. No I/O, no network.

Both pages server-render into window.__PRELOAD_DATA. A cabinet markup change
must degrade to an empty result, never a crash — that is what most of these
tests pin down.
"""

from datetime import date

import pytest

from app.scraper.yandex_sprav_chain import (
    SpravBranch,
    parse_branch_total,
    parse_chain_branches,
    parse_chain_name,
    parse_rating_history,
)


def _branch_payload(**overrides):
    raw = {
        "id": 4082902,
        "permanent_id": 17369842518,
        "displayName": "Суши Мастер",
        "publishing_status": "publish",
        "reviewsCount": 182,
        "rating": {"score": 4.4},
        "address": {
            "formatted": {"value": "Губкинский, 12-й микрорайон, 39", "locale": "ru"},
            "pos": {"type": "Point", "coordinates": [76.50596, 64.434051]},
            "components": [
                {"kind": "country", "name": {"value": "Россия"}},
                {"kind": "province", "name": {"value": "Ямало-Ненецкий автономный округ"}},
                {"kind": "locality", "name": {"value": "Губкинский"}},
                {"kind": "house", "name": {"value": "39"}},
            ],
        },
    }
    raw.update(overrides)
    return {"initialState": {"chain": {
        "chain": {"displayName": "Суши Мастер"},
        "companyList": {"companies": [raw], "pager": {"offset": 0, "limit": 20, "total": 209}},
    }}}


def test_parses_the_branch_identity_and_address():
    branch = parse_chain_branches(_branch_payload())[0]
    assert isinstance(branch, SpravBranch)
    assert branch.permanent_id == "17369842518"
    assert branch.sprav_id == "4082902"
    assert branch.city == "Губкинский"
    assert branch.region == "Ямало-Ненецкий автономный округ"
    assert branch.address == "Губкинский, 12-й микрорайон, 39"


def test_permalink_is_a_string_because_it_is_an_identifier():
    """It joins to organizations.external_id, which is TEXT — never compare ints."""
    assert parse_chain_branches(_branch_payload())[0].permanent_id == "17369842518"


def test_coordinates_are_read_lon_then_lat():
    branch = parse_chain_branches(_branch_payload())[0]
    assert branch.lon == 76.50596
    assert branch.lat == 64.434051


def test_current_rating_and_review_count_are_carried():
    branch = parse_chain_branches(_branch_payload())[0]
    assert branch.rating == 4.4
    assert branch.review_count == 182


def test_rating_may_arrive_as_a_bare_number():
    assert parse_chain_branches(_branch_payload(rating=4.1))[0].rating == 4.1


def test_branch_without_permalink_is_skipped():
    payload = _branch_payload()
    payload["initialState"]["chain"]["companyList"]["companies"].append({"displayName": "no id"})
    assert len(parse_chain_branches(payload)) == 1


def test_pager_total_and_chain_name_are_read():
    assert parse_branch_total(_branch_payload()) == 209
    assert parse_chain_name(_branch_payload()) == "Суши Мастер"


@pytest.mark.parametrize("bad", [
    {}, [], None, "", "not json", 42,
    {"initialState": None},
    {"initialState": {"chain": None}},
    {"initialState": {"chain": {"companyList": None}}},
    {"initialState": {"chain": {"companyList": {"companies": "nope"}}}},
])
def test_degenerate_branch_payloads_return_empty_without_raising(bad):
    assert parse_chain_branches(bad) == []
    assert parse_branch_total(bad) is None
    assert parse_chain_name(bad) is None


# --- rating history -------------------------------------------------------

def _history_payload(**overrides):
    data = {
        "rating_statistic": {"one": 39, "two": 10, "three": 23, "four": 29, "five": 190},
        "rating_history": [
            {"rating": 4.3, "week": 1753056000000000,
             "opponents_ratings": [{"id": 0, "rating": 4.2, "permalink": 85213801615, "name": "Osaka"}]},
            {"rating": 4.4, "week": 1753660800000000, "opponents_ratings": []},
        ],
    }
    data.update(overrides)
    return {"initialState": {"edit": {
        "ratingHistory": {"data": data},
        "factors": {"strength": 112, "factors": [
            {"name": "photos", "active": True, "strength": 20, "days_from_update": 4, "status": "normal"},
        ]},
    }}}


def test_parses_every_weekly_point():
    history = parse_rating_history(_history_payload())
    assert [p.rating for p in history.history] == [4.3, 4.4]


def test_week_microseconds_become_a_date():
    point = parse_rating_history(_history_payload()).history[0]
    assert point.week == date(2025, 7, 21)


def test_opponents_are_carried_with_string_permalinks():
    opponent = parse_rating_history(_history_payload()).history[0].opponents[0]
    assert opponent == {"name": "Osaka", "permalink": "85213801615", "rating": 4.2}


def test_star_distribution_is_read():
    assert parse_rating_history(_history_payload()).stars == {
        "one": 39, "two": 10, "three": 23, "four": 29, "five": 190,
    }


def test_card_strength_and_factors_are_read():
    history = parse_rating_history(_history_payload())
    assert history.card_strength == 112
    assert history.factors[0]["name"] == "photos"
    assert history.factors[0]["days_from_update"] == 4


def test_week_without_a_rating_is_kept_as_none_not_zero():
    """A week the cabinet published no rating for is a gap. Zero would be a lie."""
    payload = _history_payload(rating_history=[{"rating": None, "week": 1753056000000000}])
    point = parse_rating_history(payload).history[0]
    assert point.rating is None


def test_missing_star_bucket_is_none_not_zero():
    payload = _history_payload(rating_statistic={"one": 1})
    assert parse_rating_history(payload).stars["five"] is None


def test_point_without_a_parsable_week_is_dropped():
    """captured_on is NOT NULL — a point with no week cannot become a snapshot."""
    payload = _history_payload(rating_history=[{"rating": 4.0, "week": None}, {"rating": 4.1, "week": "nope"}])
    assert parse_rating_history(payload).history == []


@pytest.mark.parametrize("bad", [
    {}, [], None, "", 42,
    {"initialState": None},
    {"initialState": {"edit": {"ratingHistory": None}}},
    {"initialState": {"edit": {"ratingHistory": {"data": "nope"}}}},
    {"initialState": {"edit": {"ratingHistory": {"data": {"rating_history": "nope"}}}}},
])
def test_degenerate_history_payloads_return_empty_without_raising(bad):
    history = parse_rating_history(bad)
    assert history.history == []
    assert history.card_strength is None


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_numbers_degrade_to_none(bad):
    """json.loads accepts NaN/Infinity; neither is a rating."""
    payload = _history_payload(rating_history=[{"rating": bad, "week": 1753056000000000}])
    assert parse_rating_history(payload).history[0].rating is None
