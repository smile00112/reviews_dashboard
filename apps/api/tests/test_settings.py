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
