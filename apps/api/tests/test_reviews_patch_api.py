"""Internal triage mutations (status / paid flag). Gated by the
``action:review.edit_status`` permission (feature 016). Nothing is ever published
to external platforms."""

import uuid
from datetime import datetime, timezone

from app.models.enums import ReviewPlatform, ScrapeMode
from app.models.organization import Organization
from app.models.review import Review

NOW = datetime.now(timezone.utc)


def _seed_review(db):
    org = Organization(name="Org")
    db.add(org)
    db.commit()
    db.refresh(org)
    r = Review(
        organization_id=org.id,
        source="yandex_maps",
        scrape_mode=ScrapeMode.public,
        platform=ReviewPlatform.yandex,
        rating=1,
        review_text="text",
        content_hash="h1",
        first_seen_at=NOW,
        last_seen_at=NOW,
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


def test_patch_requires_auth(client, db_session):
    r = _seed_review(db_session)
    resp = client.patch(f"/api/reviews/{r.id}", json={"status": "escalated"})
    assert resp.status_code == 401


def test_patch_allowed_for_call_center(operator_client, db_session):
    """call_center holds action:review.edit_status → PATCH succeeds."""
    r = _seed_review(db_session)
    resp = operator_client.patch(f"/api/reviews/{r.id}", json={"status": "escalated"})
    assert resp.status_code == 200


def test_patch_forbidden_without_permission(manager_client, db_session):
    """manager lacks action:review.edit_status → 403."""
    r = _seed_review(db_session)
    resp = manager_client.patch(f"/api/reviews/{r.id}", json={"status": "escalated"})
    assert resp.status_code == 403


def test_patch_status_and_paid(admin_client, db_session):
    r = _seed_review(db_session)
    resp = admin_client.patch(
        f"/api/reviews/{r.id}",
        json={"status": "in_progress", "is_paid": True, "paid_cost": 570},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "in_progress"
    assert body["is_paid"] is True
    assert body["paid_cost"] == 570
    assert body["organization_name"] == "Org"

    # Partial update: only reset paid_cost, everything else untouched.
    resp = admin_client.patch(f"/api/reviews/{r.id}", json={"paid_cost": None})
    body = resp.json()
    assert body["paid_cost"] is None
    assert body["status"] == "in_progress"
    assert body["is_paid"] is True


def test_patch_dedup_hash_untouched(admin_client, db_session):
    r = _seed_review(db_session)
    before = r.content_hash
    admin_client.patch(f"/api/reviews/{r.id}", json={"status": "escalated"})
    db_session.refresh(r)
    assert r.content_hash == before


def test_patch_unknown_review_404(admin_client):
    resp = admin_client.patch(f"/api/reviews/{uuid.uuid4()}", json={"status": "escalated"})
    assert resp.status_code == 404


def test_patch_invalid_status_422(admin_client, db_session):
    r = _seed_review(db_session)
    resp = admin_client.patch(f"/api/reviews/{r.id}", json={"status": "published"})
    assert resp.status_code == 422


def test_patch_is_paid_explicit_null_422(admin_client, db_session):
    r = _seed_review(db_session)
    resp = admin_client.patch(f"/api/reviews/{r.id}", json={"is_paid": None})
    assert resp.status_code == 422
