from uuid import UUID

from pydantic import BaseModel, ConfigDict


class LoginRequest(BaseModel):
    email: str
    password: str


class RoleSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    slug: str
    name: str
    is_system: bool


class UserResponse(BaseModel):
    """Current user with role object and effective permission set (feature 016).

    ``permissions`` is the deny-by-default effective set the frontend mirrors for
    UX (nav/button gating); the backend remains the authoritative enforcement point.
    """

    id: UUID
    name: str
    email: str
    role: RoleSummary
    permissions: list[str]
