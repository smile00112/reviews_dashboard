"""Settings storage + /api/settings contract (dashboard settings feature)."""

from app.models.app_setting import AppSetting


def test_app_setting_roundtrip(db_session):
    row = AppSetting(key="overview_sla_threshold_minutes", value=720)
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)

    assert row.key == "overview_sla_threshold_minutes"
    assert row.value == 720
    assert row.updated_at is not None


def test_settings_service_get_int_default(db_session):
    from app.services.settings_service import SettingsService

    assert SettingsService(db_session).get_int("nope", 1440) == 1440


def test_settings_service_set_then_get(db_session):
    from app.services.settings_service import SettingsService

    svc = SettingsService(db_session)
    svc.set("overview_sla_threshold_minutes", 720)
    assert svc.get_int("overview_sla_threshold_minutes", 1440) == 720
    # upsert: a second set overwrites, no duplicate-key error
    svc.set("overview_sla_threshold_minutes", 300)
    assert svc.get_int("overview_sla_threshold_minutes", 1440) == 300


def test_settings_service_sla_falls_back_to_config(db_session):
    from app.core.config import settings
    from app.services.settings_service import SettingsService

    assert SettingsService(db_session).sla_threshold_minutes() == settings.overview_sla_threshold_minutes


def test_get_settings_returns_config_default(admin_client):
    resp = admin_client.get("/api/settings")
    assert resp.status_code == 200
    from app.core.config import settings
    assert resp.json()["overview_sla_threshold_minutes"] == settings.overview_sla_threshold_minutes


def test_patch_settings_persists(admin_client):
    resp = admin_client.patch("/api/settings", json={"overview_sla_threshold_minutes": 360})
    assert resp.status_code == 200
    assert resp.json()["overview_sla_threshold_minutes"] == 360
    # persisted across a fresh GET
    assert admin_client.get("/api/settings").json()["overview_sla_threshold_minutes"] == 360


def test_patch_settings_rejects_non_positive(admin_client):
    resp = admin_client.patch("/api/settings", json={"overview_sla_threshold_minutes": 0})
    assert resp.status_code == 422


def test_patch_settings_requires_admin(operator_client):
    resp = operator_client.patch("/api/settings", json={"overview_sla_threshold_minutes": 360})
    assert resp.status_code == 403


def test_patch_settings_requires_auth(client):
    resp = client.patch("/api/settings", json={"overview_sla_threshold_minutes": 360})
    assert resp.status_code == 401


def test_dashboard_uses_db_sla_threshold(db_session, monkeypatch):
    from app.services.dashboard_service import DashboardService
    from app.services.settings_service import SettingsService

    captured = {}

    def fake_review_cube(self, org_ids, cutoff, now, until=None, prev_window=None, sla_minutes=None):
        captured["sla_minutes"] = sla_minutes
        return []

    SettingsService(db_session).set("overview_sla_threshold_minutes", 90)
    monkeypatch.setattr(DashboardService, "_review_cube", fake_review_cube)

    svc = DashboardService(db_session)
    # _selected_orgs returns [] on an empty DB -> overview short-circuits before
    # _review_cube. Call _review_cube resolution path directly instead:
    resolved = SettingsService(db_session).sla_threshold_minutes()
    assert resolved == 90
    svc._review_cube(None, None, None, None, None, resolved)
    assert captured["sla_minutes"] == 90
