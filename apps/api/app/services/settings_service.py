"""Read/write for the app_settings key-value store (dashboard settings feature).

Reads fall back to the config default when the row is absent, so the feature
works before any value has ever been saved. Upsert is select-then-write (no
dialect-specific ON CONFLICT) so the SQLite test backend works.
"""

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.app_setting import AppSetting

SLA_KEY = "overview_sla_threshold_minutes"


class SettingsService:
    def __init__(self, db: Session):
        self.db = db

    def get_int(self, key: str, default: int) -> int:
        row = self.db.get(AppSetting, key)
        if row is None:
            return default
        try:
            return int(row.value)
        except (TypeError, ValueError):
            return default

    def set(self, key: str, value) -> AppSetting:
        row = self.db.get(AppSetting, key)
        if row is None:
            row = AppSetting(key=key, value=value)
            self.db.add(row)
        else:
            row.value = value
        self.db.commit()
        self.db.refresh(row)
        return row

    def sla_threshold_minutes(self) -> int:
        return self.get_int(SLA_KEY, settings.overview_sla_threshold_minutes)
