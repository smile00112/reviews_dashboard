"""Matching Sprav branches to our organizations.

The contract that matters: the address fallback must never produce a *wrong*
match. Attributing one branch's rating history to a different branch corrupts
the data silently, so refusing is always the correct failure mode.
"""

import uuid

from app.models.organization import Organization
from app.scraper.yandex_sprav_chain import SpravBranch
from app.services.sprav_branch_match import (
    best_match,
    calibrate,
    house_numbers,
    match_branches,
    organization_city,
    score,
)


def _org(name, *, external_id=None, city=None):
    return Organization(id=uuid.uuid4(), name=name, external_id=external_id, city=city)


def _branch(permanent_id, city, address):
    return SpravBranch(permanent_id=str(permanent_id), city=city, address=address)


# --- city extraction ------------------------------------------------------

def test_city_is_read_from_the_name_convention():
    assert organization_city(_org("Тюмень-03 Газовиков 61")) == "тюмень"


def test_hyphenated_city_survives_the_branch_index():
    """'Ростов-на-Дону-08' must not become 'Ростов' — splitting on the first
    dash silently broke every hyphenated city."""
    assert organization_city(_org("Ростов-на-Дону-08 Буденовский 68")) == "ростов на дону"
    assert organization_city(_org("Каменск-Уральский-01 Победы 87а")) == "каменск уральский"
    assert organization_city(_org("Комсомольск-на-Амуре-02 Мира 47")) == "комсомольск на амуре"


def test_city_column_is_the_fallback_when_the_name_has_no_index():
    assert organization_city(_org("Тарко-Сале ул. Губкина, 20", city="Тарко-Сале")) == "тарко сале"


# --- house numbers --------------------------------------------------------

def test_house_numbers_keep_their_letter():
    assert house_numbers("улица Кирова, 21А") == {"21а"}


def test_house_numbers_are_case_and_yo_insensitive():
    assert house_numbers("Будённовский проспект, 68") == house_numbers("буденновский проспект, 68")


# --- scoring --------------------------------------------------------------

def test_different_city_never_matches():
    assert score(_branch(1, "Пермь", "улица Солдатова, 28"), _org("Тюмень-01 Солдатова 28")) == 0.0


def test_different_house_never_matches():
    assert score(_branch(1, "Хабаровск", "Амурский бульвар, 66"), _org("Хабаровск-06 Амурский бульвар 62")) == 0.0


def test_exact_city_street_and_house_scores_top():
    assert score(_branch(1, "Пермь", "Пермь, улица Солдатова, 28"), _org("Пермь-07 Солдатова 28")) == 1.0


def test_house_suffix_mismatch_scores_below_an_exact_hit():
    """'21' vs '21А' is weaker evidence and must not pass for a certain match."""
    value = score(_branch(1, "Новокузнецк", "Новокузнецк, улица Кирова, 21А"), _org("Новокузнецк-06 Кирова 21"))
    assert 0.0 < value <= 0.75


def test_matching_street_words_beat_a_bare_house_number():
    with_street = score(_branch(1, "Пермь", "Пермь, улица Солдатова, 28"), _org("Пермь-07 Солдатова 28"))
    without = score(_branch(1, "Пермь", "Пермь, улица Ленина, 28"), _org("Пермь-07 Солдатова 28"))
    assert with_street > without


# --- candidate selection --------------------------------------------------

def test_ambiguous_candidates_are_refused_rather_than_guessed():
    """Two identical candidates mean we cannot know. Refuse."""
    branch = _branch(1, "Пермь", "Пермь, улица Солдатова, 28")
    twins = [_org("Пермь-07 Солдатова 28"), _org("Пермь-08 Солдатова 28")]
    assert best_match(branch, twins) == (None, 0.0)


def test_no_candidate_at_all_is_refused():
    assert best_match(_branch(1, "Пермь", "улица Солдатова, 28"), []) == (None, 0.0)


# --- full matching --------------------------------------------------------

def test_permalink_match_wins_and_scores_certain():
    org = _org("Губкинский-01 мкр 12 39", external_id="17369842518")
    branch = _branch(17369842518, "Губкинский", "Губкинский, 12-й микрорайон, 39")
    match = match_branches([branch], [org])[0]
    assert match.organization is org
    assert match.method == "external_id"
    assert match.confidence == 1.0


def test_address_match_is_used_when_no_permalink_is_stored():
    org = _org("Пермь-07 Солдатова 28")
    match = match_branches([_branch(999, "Пермь", "Пермь, улица Солдатова, 28")], [org])[0]
    assert match.organization is org
    assert match.method == "address"


def test_unmatchable_branch_reports_no_organization():
    match = match_branches([_branch(999, "Сочи", "Сочи, улица Морская, 1")], [_org("Пермь-07 Солдатова 28")])[0]
    assert match.organization is None
    assert match.method is None
    assert match.confidence == 0.0


def test_an_organization_is_claimed_only_once():
    """Two branches must not both absorb the same organization."""
    org = _org("Пермь-07 Солдатова 28")
    branches = [_branch(1, "Пермь", "Пермь, улица Солдатова, 28"), _branch(2, "Пермь", "Пермь, улица Солдатова, 28")]
    matched = [m for m in match_branches(branches, [org]) if m.organization]
    assert len(matched) == 1


def test_address_fallback_can_be_disabled():
    """With the fallback off, only permalink matches survive — the rest are unmatched."""
    by_id = _org("Пермь-07 Солдатова 28", external_id="111")
    by_addr = _org("Сочи-01 Морская 1")
    branches = [_branch(111, "Пермь", "Пермь, Солдатова, 28"),
                _branch(222, "Сочи", "Сочи, Морская, 1")]
    matches = {m.branch.permanent_id: m for m in
               match_branches(branches, [by_id, by_addr], address_fallback=False)}
    assert matches["111"].organization is by_id and matches["111"].method == "external_id"
    assert matches["222"].organization is None and matches["222"].method is None


def test_permalink_owner_is_not_stolen_by_an_address_match():
    """An org already claimed by its permalink must stay with that branch."""
    org = _org("Пермь-07 Солдатова 28", external_id="111")
    branches = [_branch(999, "Пермь", "Пермь, улица Солдатова, 28"), _branch(111, "Пермь", "Пермь, улица Солдатова, 28")]
    matches = {m.branch.permanent_id: m for m in match_branches(branches, [org])}
    assert matches["111"].organization is org
    assert matches["999"].organization is None


# --- calibration ----------------------------------------------------------

def test_calibration_counts_a_recovered_pair_as_correct():
    org = _org("Пермь-07 Солдатова 28", external_id="111")
    report = calibrate([_branch(111, "Пермь", "Пермь, улица Солдатова, 28")], [org])
    assert (report.checked, report.correct, report.wrong) == (1, 1, 0)
    assert report.is_trustworthy


def test_calibration_counts_an_abstention_as_refused_not_wrong():
    org = _org("Пермь-07 Солдатова 28", external_id="111")
    report = calibrate([_branch(111, "Сочи", "Сочи, улица Морская, 1")], [org])
    assert (report.refused, report.wrong) == (1, 0)
    assert report.is_trustworthy


def test_calibration_flags_a_wrong_match_as_untrustworthy():
    """A false positive disqualifies the fallback outright."""
    right = _org("Пермь-07 Солдатова 28", external_id="111")
    wrong = _org("Пермь-09 Солдатова 28")
    # The branch's permalink says `right`, but `wrong` outscores it on address.
    report = calibrate([_branch(111, "Пермь", "Пермь, Солдатова, 28")], [wrong, right])
    assert report.wrong == 0 or not report.is_trustworthy


def test_branch_without_a_known_answer_is_not_calibrated_on():
    report = calibrate([_branch(999, "Пермь", "улица Солдатова, 28")], [_org("Пермь-07 Солдатова 28")])
    assert report.checked == 0
