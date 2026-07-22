"""Permission enforcement tests (feature 016, User Story 2).

The backend is the source of truth: every mutating route is guarded by a specific
``require_permission(...)``. For each gate we assert:
  - anonymous          → 401 (no session)
  - role lacking perm  → 403 (call_center operator lacks all admin-side actions)
  - role with perm     → NOT 401/403 (admin passes every gate; operator passes its own)

Deny/401 happen in the dependency before the endpoint body, so representative
payloads/ids are enough — we never reach business logic on a refused request.
"""

import uuid

import pytest

DUMMY = str(uuid.uuid4())

# (method, path, action-permission) for each guarded mutation.
GATED = [
    ("post", "/api/organizations", "action:org.manage"),
    ("post", "/api/companies", "action:company.manage"),
    ("post", "/api/scrape/all", "action:scrape.run"),
    ("post", f"/api/jobs/{DUMMY}/run", "action:job.manage"),
    ("patch", f"/api/reviews/{DUMMY}", "action:review.edit_status"),
    ("post", "/api/attention-rules", "action:attention.manage"),
    ("patch", "/api/settings", "action:settings.edit"),
    ("post", "/api/scraper/yandex/session/check", "action:scraper_session.manage"),
]


def _call(client, method, path):
    return getattr(client, method)(path, json={})


@pytest.mark.parametrize("method,path,perm", GATED)
def test_anonymous_gets_401(client, method, path, perm):
    resp = _call(client, method, path)
    assert resp.status_code == 401, f"{perm}: expected 401, got {resp.status_code}"


@pytest.mark.parametrize("method,path,perm", GATED)
def test_role_without_permission_gets_403(operator_client, method, path, perm):
    # call_center (operator) holds only page:* + action:review.edit_status.
    resp = _call(operator_client, method, path)
    if perm == "action:review.edit_status":
        # operator HAS this one → must pass the gate (404 for the dummy id, not 403)
        assert resp.status_code not in (401, 403), f"{perm}: operator should pass gate"
    else:
        assert resp.status_code == 403, f"{perm}: expected 403, got {resp.status_code}"


@pytest.mark.parametrize("method,path,perm", GATED)
def test_admin_passes_every_gate(admin_client, method, path, perm):
    resp = _call(admin_client, method, path)
    assert resp.status_code not in (401, 403), (
        f"{perm}: admin must pass the gate, got {resp.status_code}"
    )
