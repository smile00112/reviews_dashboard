from app.admin.auth import AdminAuth
from app.admin.base import RoleAwareAdmin
from app.admin.views import OrganizationAdmin, ReviewAdmin, UserAdmin
from app.core.config import settings


def setup_admin(app, engine) -> RoleAwareAdmin:
    auth_backend = AdminAuth(secret_key=settings.admin_secret_key)
    admin = RoleAwareAdmin(
        app, engine,
        base_url="/admin",
        title="SERM Admin",
        authentication_backend=auth_backend,
    )
    admin.add_view(UserAdmin)
    admin.add_view(OrganizationAdmin)
    admin.add_view(ReviewAdmin)
    return admin
