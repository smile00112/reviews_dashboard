"""Pure parser for the Sprav cabinet companies payload. No I/O, no network.

The cabinet server-renders its company list into window.__PRELOAD_DATA; the
fixture is that structure, scrubbed of everything except business data.
"""

import json
from pathlib import Path

import pytest

from app.scraper.yandex_sprav import SpravOrg, extract_preload_data, parse_sprav_orgs

FIXTURE = Path(__file__).parent / "fixtures" / "sprav_companies_preload.json"


@pytest.fixture
def preload():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_parses_every_organization(preload):
    orgs = parse_sprav_orgs(preload)
    assert len(orgs) == 2
    assert all(isinstance(o, SpravOrg) for o in orgs)


def test_every_organization_has_identity(preload):
    for org in parse_sprav_orgs(preload):
        assert org.sprav_id
        assert org.name


def test_maps_the_chain_fields(preload):
    """The 357-branch chain is the first record; its permalink is the Maps id."""
    org = parse_sprav_orgs(preload)[0]
    assert org.sprav_id == "81562141869"
    assert org.org_type == "chain"
    assert org.branch_count == 357
    assert org.publishing_status == "publish"
    assert org.url == "https://sushi-master.ru/"


def test_address_is_flattened_from_the_formatted_dict(preload):
    """address.formatted is {"value": ..., "locale": ...}, not a string."""
    org = parse_sprav_orgs(preload)[0]
    assert isinstance(org.address, str)


def test_only_the_main_url_is_taken(preload):
    """The record also carries a 'social' url; it must not win."""
    org = parse_sprav_orgs(preload)[0]
    assert "vk.com" not in (org.url or "")


@pytest.mark.parametrize("bad", [
    {},
    [],
    None,
    "",
    "not json at all",
    {"unexpected": "shape"},
    {"initialState": None},
    {"initialState": {"companiesList": None}},
    {"initialState": {"companiesList": {"listCompanies": None}}},
    {"initialState": {"companiesList": {"listCompanies": "nope"}}},
    42,
])
def test_degenerate_payloads_return_empty_without_raising(bad):
    """Safe degradation: a cabinet change must surface as an empty run, never a crash."""
    assert parse_sprav_orgs(bad) == []


def test_record_without_identity_is_skipped():
    payload = {"initialState": {"companiesList": {"listCompanies": [
        {"displayName": "no id here"},
        {"permanent_id": 123},
        {"permanent_id": 456, "displayName": "keeper"},
    ]}}}
    orgs = parse_sprav_orgs(payload)
    assert len(orgs) == 1
    assert orgs[0].sprav_id == "456"


def test_record_missing_optional_fields_still_parses():
    payload = {"initialState": {"companiesList": {"listCompanies": [
        {"permanent_id": 999, "displayName": "Bare"},
    ]}}}
    org = parse_sprav_orgs(payload)[0]
    assert org.address is None
    assert org.url is None
    assert org.branch_count is None
    assert org.publishing_status is None


@pytest.mark.parametrize("bad_branch_count", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_branch_count_yields_none_without_raising(bad_branch_count):
    """json.loads accepts NaN/Infinity/-Infinity; int() on those raises. Must degrade to None."""
    payload = {"initialState": {"companiesList": {"listCompanies": [
        {"permanent_id": 1, "displayName": "Weird", "chain": {"branchCount": bad_branch_count}},
    ]}}}
    orgs = parse_sprav_orgs(payload)
    assert len(orgs) == 1
    assert orgs[0].branch_count is None


def test_extract_preload_data_reads_the_inline_script():
    html = '<html><script nonce="">window.__PRELOAD_DATA = {"a": {"b": 1}};</script></html>'
    assert extract_preload_data(html) == {"a": {"b": 1}}


@pytest.mark.parametrize("html", [
    "",
    "<html>nothing here</html>",
    "<html><script>window.__PRELOAD_DATA = not-json;</script></html>",
    "<html><script>window.__OTHER = {\"a\": 1};</script></html>",
])
def test_extract_preload_data_returns_empty_on_anything_unexpected(html):
    assert extract_preload_data(html) == {}
