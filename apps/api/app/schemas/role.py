from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PermissionItem(BaseModel):
    key: str
    label: str


class PermissionCatalog(BaseModel):
    pages: list[PermissionItem]
    actions: list[PermissionItem]


class RoleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    slug: str
    name: str
    is_system: bool
    description: str | None = None
    # For the admin system role this is the sentinel ["*"] meaning "all".
    permissions: list[str]
    user_count: int


class RoleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = None
    permissions: list[str] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def _strip_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("name must not be blank")
        return v


class RoleUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=100)
    description: str | None = None

    @field_validator("name")
    @classmethod
    def _strip_name(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        if not v:
            raise ValueError("name must not be blank")
        return v


class GrantUpdate(BaseModel):
    permissions: list[str]
