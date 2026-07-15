"""Sprav org-list CLI: serialization and exit-code contract."""

import json

from app.scraper.yandex_sprav import SpravListResult, SpravOrg
from scripts.sprav_orgs import exit_code_for, orgs_to_json


def _org():
    return SpravOrg(
        sprav_id="81562141869",
        name="Суши Мастер",
        address="Земля",
        url="https://sushi-master.ru/",
        org_type="chain",
        branch_count=357,
        publishing_status="publish",
    )


def test_orgs_to_json_roundtrips_all_fields():
    payload = json.loads(orgs_to_json([_org()], pretty=False))
    assert payload == [{
        "sprav_id": "81562141869",
        "name": "Суши Мастер",
        "address": "Земля",
        "url": "https://sushi-master.ru/",
        "org_type": "chain",
        "branch_count": 357,
        "publishing_status": "publish",
    }]


def test_orgs_to_json_keeps_cyrillic_readable():
    assert "Суши Мастер" in orgs_to_json([_org()], pretty=False)


def test_orgs_to_json_pretty_is_indented():
    assert "\n  " in orgs_to_json([_org()], pretty=True)


def test_empty_list_serializes_to_empty_array():
    assert json.loads(orgs_to_json([], pretty=False)) == []


def test_exit_code_success():
    assert exit_code_for(SpravListResult(organizations=[_org()])) == 0


def test_exit_code_needs_manual_action():
    assert exit_code_for(SpravListResult(needs_manual_action=True, error_code="access_challenge")) == 2


def test_exit_code_error():
    assert exit_code_for(SpravListResult(error_code="sprav_scrape_error")) == 1


def test_exit_code_empty_result_is_not_success():
    """No orgs and no error still means the run told us nothing — do not exit 0."""
    assert exit_code_for(SpravListResult()) == 1
