"""Contract for the Sprav → organizations sync plan.

The rules that must not silently change:

* deactivation fires **only** for an external_id-confirmed absence — a point
  with no external_id is never deactivated, however unmatched.
* the normalized_url rule branches on external_id: known id → no edit/main and
  update only on id change; unknown id → fill from the resolver.
* rating / review_count are never written.
"""

import uuid

from app.models.organization import Organization
from app.scraper.yandex_sprav_chain import SpravBranch
from app.services.sprav_branch_match import match_branches
from app.services.sprav_sync import (
    apply_plan,
    build_plan,
    maps_url_for,
    permanent_id_in_url,
)


def _org(name, *, external_id=None, city=None, region=None, address=None,
         normalized_url=None, is_active=True):
    return Organization(
        id=uuid.uuid4(), name=name, external_id=external_id, city=city,
        region=region, address=address, normalized_url=normalized_url,
        is_active=is_active,
    )


def _branch(permanent_id, *, city=None, address=None, name=None, region=None,
            publishing_status="publish", rating=None, review_count=None):
    return SpravBranch(
        permanent_id=str(permanent_id), city=city, address=address, name=name,
        region=region, publishing_status=publishing_status, rating=rating,
        review_count=review_count,
    )


def _plan(branches, orgs, resolver=lambda b: None):
    return build_plan(match_branches(branches, orgs), orgs, resolver)


# --- helpers --------------------------------------------------------------

def test_permanent_id_is_read_with_or_without_a_slug():
    assert permanent_id_in_url("https://yandex.ru/maps/org/17369842518") == "17369842518"
    assert permanent_id_in_url("https://yandex.ru/maps/org/sushi_master/17369842518") == "17369842518"


def test_short_code_link_carries_no_permanent_id():
    assert permanent_id_in_url("https://yandex.ru/maps/-/CCU8abc") is None
    assert permanent_id_in_url(None) is None


# --- deactivation safety --------------------------------------------------

def test_point_with_external_id_absent_from_cabinet_is_deactivated():
    org = _org("Пермь-07 Солдатова 28", external_id="111")
    plan = _plan([_branch(999, city="Сочи", address="Сочи, Морская, 1")], [org])
    assert plan.deactivate == [org]
    assert plan.ambiguous == []


def test_point_without_external_id_is_never_deactivated():
    """The dangerous case: no external_id + no match must NOT be deactivated."""
    org = _org("Пермь-07 Солдатова 28")  # no external_id
    plan = _plan([_branch(999, city="Сочи", address="Сочи, Морская, 1")], [org])
    assert plan.deactivate == []
    assert plan.ambiguous == [org]


def test_present_point_is_not_deactivated():
    org = _org("Губкинский-01 мкр 12 39", external_id="17369842518")
    branch = _branch(17369842518, city="Губкинский", address="Губкинский, 12-й микрорайон, 39")
    plan = _plan([branch], [org])
    assert plan.deactivate == []


def test_partial_read_never_deactivates():
    """allow_deactivation=False (truncated branch list) must suppress deactivation."""
    org = _org("Пермь-07 Солдатова 28", external_id="111")
    matches = match_branches([_branch(999, city="Сочи", address="Сочи, Морская, 1")], [org])
    plan = build_plan(matches, [org], lambda b: None, allow_deactivation=False)
    assert plan.deactivate == []  # would be [org] with a complete read


def test_already_inactive_point_is_not_re_deactivated():
    org = _org("Пермь-07 Солдатова 28", external_id="111", is_active=False)
    plan = _plan([_branch(999, city="Сочи", address="Сочи, Морская, 1")], [org])
    assert plan.deactivate == []


# --- new in cabinet -------------------------------------------------------

def test_unmatched_open_branch_is_reported_as_new():
    branch = _branch(999, city="Сочи", address="Сочи, Морская, 1")  # publish by default
    plan = _plan([branch], [_org("Пермь-07 Солдатова 28", external_id="111")])
    assert plan.new_in_cabinet == [branch]
    assert plan.skipped_closed == []


def test_unmatched_closed_branch_is_not_pulled_in():
    """A closed branch we never had must not land in new_in_cabinet."""
    branch = _branch(999, city="Сочи", address="Сочи, Морская, 1", publishing_status="closed")
    plan = _plan([branch], [_org("Пермь-07 Солдатова 28", external_id="111")])
    assert plan.new_in_cabinet == []
    assert plan.skipped_closed == [branch]


def test_unmatched_temporarily_closed_branch_is_not_pulled_in():
    branch = _branch(999, city="Сочи", address="Сочи, Морская, 1",
                     publishing_status="temporarily_closed")
    plan = _plan([branch], [_org("Пермь-07 Солдатова 28", external_id="111")])
    assert plan.new_in_cabinet == []
    assert plan.skipped_closed == [branch]


# --- field updates --------------------------------------------------------

def test_region_fills_only_when_ours_is_empty():
    org = _org("Губкинский-01 мкр 12 39", external_id="1", region=None,
               normalized_url="https://yandex.ru/maps/org/1")
    branch = _branch(1, city="Губкинский", address="Губкинский, 12-й микрорайон, 39",
                     region="Уральский федеральный округ")
    plan = _plan([branch], [org])
    assert plan.update[0].changes["region"] == (None, "Уральский федеральный округ")


def test_region_is_not_overwritten_when_present():
    org = _org("Губкинский-01 мкр 12 39", external_id="1", region="Старый регион",
               normalized_url="https://yandex.ru/maps/org/1")
    branch = _branch(1, city="Губкинский", address="Губкинский, 12-й микрорайон, 39",
                     region="Уральский федеральный округ")
    plan = _plan([branch], [org])
    changes = plan.update[0].changes if plan.update else {}
    assert "region" not in changes


def test_closed_status_deactivates_a_matched_point():
    org = _org("Губкинский-01 мкр 12 39", external_id="1",
               normalized_url="https://yandex.ru/maps/org/1")
    branch = _branch(1, city="Губкинский", address="Губкинский, 12-й микрорайон, 39",
                     publishing_status="closed")
    plan = _plan([branch], [org])
    assert plan.update[0].changes["is_active"] == (True, False)


def test_publish_status_never_reactivates():
    org = _org("Губкинский-01 мкр 12 39", external_id="1", is_active=False,
               normalized_url="https://yandex.ru/maps/org/1")
    branch = _branch(1, city="Губкинский", address="Губкинский, 12-й микрорайон, 39",
                     publishing_status="publish")
    plan = _plan([branch], [org])
    changes = plan.update[0].changes if plan.update else {}
    assert "is_active" not in changes


def test_rating_and_review_count_are_never_written():
    org = _org("Губкинский-01 мкр 12 39", external_id="1",
               normalized_url="https://yandex.ru/maps/org/1")
    branch = _branch(1, city="Губкинский", address="Губкинский, 12-й микрорайон, 39",
                     rating=4.9, review_count=999)
    plan = _plan([branch], [org])
    changes = plan.update[0].changes if plan.update else {}
    assert "rating" not in changes and "review_count" not in changes


# --- normalized_url rule --------------------------------------------------

def test_matched_with_external_id_keeps_slug_when_id_matches():
    """Same permanent_id → don't touch normalized_url (keep the slug), no resolver call."""
    calls = []
    org = _org("Губкинский-01 мкр 12 39", external_id="17369842518",
               normalized_url="https://yandex.ru/maps/org/sushi_master/17369842518")
    branch = _branch(17369842518, city="Губкинский", address="Губкинский, 12-й микрорайон, 39")
    plan = build_plan(match_branches([branch], [org]), [org],
                      lambda b: calls.append(b) or "should-not-be-called")
    changes = plan.update[0].changes if plan.update else {}
    assert "normalized_url" not in changes
    assert calls == []  # resolver never invoked for a point that has external_id


def test_matched_with_external_id_updates_url_when_embedded_id_differs():
    """Stale normalized_url pointing at an old id → rewrite to the new card."""
    org = _org("Губкинский-01 мкр 12 39", external_id="17369842518",
               normalized_url="https://yandex.ru/maps/org/999999")
    branch = _branch(17369842518, city="Губкинский", address="Губкинский, 12-й микрорайон, 39")
    plan = _plan([branch], [org])
    assert plan.update[0].changes["normalized_url"] == (
        "https://yandex.ru/maps/org/999999",
        maps_url_for("17369842518"),
    )


def test_matched_without_external_id_fills_from_resolver():
    """Address-matched point with a /maps/-/CODE url → resolver fills id + url."""
    org = _org("Пермь-07 Солдатова 28", normalized_url="https://yandex.ru/maps/-/CCU8abc")
    branch = _branch(555, city="Пермь", address="Пермь, улица Солдатова, 28")
    resolved = maps_url_for("555")
    plan = build_plan(match_branches([branch], [org]), [org], lambda b: resolved)
    changes = plan.update[0].changes
    assert changes["external_id"] == (None, "555")
    assert changes["normalized_url"] == ("https://yandex.ru/maps/-/CCU8abc", resolved)


def test_resolver_throttled_leaves_the_point_untouched():
    """A None from the resolver (throttled) must not blank external_id/url."""
    org = _org("Пермь-07 Солдатова 28", normalized_url="https://yandex.ru/maps/-/CCU8abc")
    branch = _branch(555, city="Пермь", address="Пермь, улица Солдатова, 28")
    plan = build_plan(match_branches([branch], [org]), [org], lambda b: None)
    changes = plan.update[0].changes if plan.update else {}
    assert "external_id" not in changes and "normalized_url" not in changes


def test_resolver_called_only_for_points_without_external_id():
    calls = []
    has_id = _org("Губкинский-01 мкр 12 39", external_id="1",
                  normalized_url="https://yandex.ru/maps/org/1")
    no_id = _org("Пермь-07 Солдатова 28", normalized_url="https://yandex.ru/maps/-/CC")
    branches = [
        _branch(1, city="Губкинский", address="Губкинский, 12-й микрорайон, 39"),
        _branch(555, city="Пермь", address="Пермь, улица Солдатова, 28"),
    ]

    def resolver(b):
        calls.append(b.permanent_id)
        return maps_url_for(b.permanent_id)

    build_plan(match_branches(branches, [has_id, no_id]), [has_id, no_id], resolver)
    assert calls == ["555"]


# --- apply ----------------------------------------------------------------

def test_apply_writes_deactivation_and_updates():
    dead = _org("Пермь-07 Солдатова 28", external_id="111")
    matched = _org("Губкинский-01 мкр 12 39", external_id="1", region=None,
                   normalized_url="https://yandex.ru/maps/org/1")
    branches = [
        _branch(1, city="Губкинский", address="Губкинский, 12-й микрорайон, 39",
                region="Уральский федеральный округ"),
        _branch(999, city="Сочи", address="Сочи, Морская, 1"),
    ]
    orgs = [dead, matched]
    plan = _plan(branches, orgs)
    counts = apply_plan(plan)
    assert dead.is_active is False
    assert matched.region == "Уральский федеральный округ"
    assert counts["deactivated"] == 1 and counts["updated"] == 1
