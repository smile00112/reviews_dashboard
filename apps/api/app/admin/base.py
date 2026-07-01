from contextvars import ContextVar

from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import Response
from sqladmin import Admin, ModelView

# Per-async-task context: set before scaffold_form is called so per-role
# form filtering is safe under concurrent requests.
_role_ctx: ContextVar[str | None] = ContextVar("_role_ctx", default=None)


class RoleAwareAdmin(Admin):
    """Admin subclass that:
    1. Propagates the request role into a contextvar before form scaffolding.
    2. Delegates per-request create/delete permission to the view's
       `can_create_for_role` / `can_delete_for_role` hooks (if defined).
    """

    async def _create(self, request: Request) -> None:
        identity = request.path_params.get("identity")
        model_view = self._find_model_view(identity)
        if hasattr(model_view, "can_create_for_role"):
            role = request.session.get("role")
            if not model_view.can_create_for_role(role):
                raise HTTPException(status_code=403)
        await super()._create(request)

    async def _delete(self, request: Request) -> None:
        identity = request.path_params.get("identity")
        model_view = self._find_model_view(identity)
        if hasattr(model_view, "can_delete_for_role"):
            role = request.session.get("role")
            if not model_view.can_delete_for_role(role):
                raise HTTPException(status_code=403)
        await super()._delete(request)

    async def edit(self, request: Request) -> Response:
        token = _role_ctx.set(request.session.get("role"))
        try:
            return await super().edit(request)
        finally:
            _role_ctx.reset(token)

    async def create(self, request: Request) -> Response:
        token = _role_ctx.set(request.session.get("role"))
        try:
            return await super().create(request)
        finally:
            _role_ctx.reset(token)


class RoleGatedModelView(ModelView):
    """Base view that exposes a role helper from the session."""

    def _get_role(self, request: Request) -> str | None:
        return request.session.get("role")
