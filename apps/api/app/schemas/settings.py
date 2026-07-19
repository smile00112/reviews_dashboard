from pydantic import BaseModel, ConfigDict, Field


class SettingsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    overview_sla_threshold_minutes: int


class SettingsUpdate(BaseModel):
    # Minutes; must be at least 1 (0/negative SLA is meaningless).
    overview_sla_threshold_minutes: int = Field(ge=1)
