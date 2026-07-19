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
