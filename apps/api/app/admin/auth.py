import uuid

from starlette.requests import Request
from starlette.responses import RedirectResponse
from sqladmin.authentication import AuthenticationBackend

from app.core.database import SessionLocal
from app.core.security import verify_password
from app.models.user import User


class AdminAuth(AuthenticationBackend):
    async def login(self, request: Request) -> bool:
        form = await request.form()
        email = form.get("username")
        password = form.get("password")
        if not email or not password:
            return False

        db = SessionLocal()
        try:
            user = db.query(User).filter(User.email == email).first()
        finally:
            db.close()

        if not user or not user.is_active:
            return False
        if not verify_password(str(password), user.password_hash):
            return False

        request.session["user_id"] = str(user.id)
        # Prefer the legacy enum value (feature 004 sqladmin views still gate on
        # "admin"/"review_operator" strings); fall back to the new role slug so a
        # user whose legacy column is NULL (feature 016) never crashes login.
        if user.role is not None:
            request.session["role"] = user.role.value
        elif user.role_ref is not None:
            request.session["role"] = user.role_ref.slug
        else:
            request.session["role"] = ""
        return True

    async def logout(self, request: Request) -> bool:
        request.session.clear()
        return True

    async def authenticate(self, request: Request):
        user_id = request.session.get("user_id")
        if not user_id:
            return RedirectResponse(request.url_for("admin:login"), status_code=302)

        db = SessionLocal()
        try:
            user = db.query(User).filter(User.id == uuid.UUID(user_id)).first()
        finally:
            db.close()

        if not user or not user.is_active:
            return RedirectResponse(request.url_for("admin:login"), status_code=302)

        return user
