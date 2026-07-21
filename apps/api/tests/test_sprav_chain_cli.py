"""sprav_chain_ratings document assembly — the --fill-missing carry-forward.

A resumed run must never drop histories an earlier run already collected.
"""

from app.scraper.yandex_sprav_chain import RatingHistory, RatingPoint, SpravBranch
from app.services.sprav_branch_match import BranchMatch
from datetime import date

from scripts.sprav_chain_ratings import build_document


def _match(permalink, city="Пермь", address="Пермь, Солдатова, 28"):
    return BranchMatch(SpravBranch(permanent_id=permalink, city=city, address=address), None, None, 0.0)


def _history(rating=4.5):
    return RatingHistory(history=[RatingPoint(week=date(2026, 7, 6), rating=rating, opponents=[])])


def test_freshly_fetched_history_is_serialized():
    doc = build_document("1", "Chain", [_match("100")], {"100": _history(4.2)})
    record = doc["records"][0]
    assert record["history"] == [{"week": "2026-07-06", "rating": 4.2, "opponents": []}]
    assert record["history_error"] is None


def test_prior_history_is_carried_forward_when_not_refetched():
    """--fill-missing: a branch not refetched keeps its earlier history."""
    carried = [{"week": "2026-06-01", "rating": 4.0, "opponents": []}]
    doc = build_document("1", "Chain", [_match("100")], histories={}, prior_history={"100": carried})
    record = doc["records"][0]
    assert record["history"] == carried
    assert record["history_error"] is None


def test_fresh_history_wins_over_carried():
    doc = build_document("1", "Chain", [_match("100")], {"100": _history(4.9)},
                         prior_history={"100": [{"week": "2026-06-01", "rating": 4.0, "opponents": []}]})
    assert doc["records"][0]["history"][0]["rating"] == 4.9


def test_branch_with_neither_fresh_nor_prior_is_marked_not_collected():
    doc = build_document("1", "Chain", [_match("100")], histories={}, prior_history={})
    record = doc["records"][0]
    assert record["history"] == []
    assert record["history_error"] == "not_collected"
