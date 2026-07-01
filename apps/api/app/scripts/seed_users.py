"""Seed initial admin and operator users. Idempotent — skips existing emails."""

import os
import sys

from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models.enums import UserRole
from app.models.user import User


def _seed(db, email: str, name: str, role: UserRole, password: str) -> None:
    existing = db.query(User).filter(User.email == email).first()
    if existing:
        print(f"SKIP  {email} (already exists)")
        return
    user = User(
        name=name,
        email=email,
        role=role,
        password_hash=hash_password(password),
        is_active=True,
    )
    db.add(user)
    db.commit()
    print(f"OK    {email} ({role.value})")


def main() -> None:
    admin_email = os.environ.get("ADMIN_EMAIL", "admin@example.com")
    admin_password = os.environ.get("ADMIN_PASSWORD", "")
    operator_email = os.environ.get("OPERATOR_EMAIL", "operator@example.com")
    operator_password = os.environ.get("OPERATOR_PASSWORD", "")

    missing = []
    if not admin_password:
        missing.append("ADMIN_PASSWORD")
    if not operator_password:
        missing.append("OPERATOR_PASSWORD")
    if missing:
        print(f"ERROR missing env vars: {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)

    db = SessionLocal()
    try:
        _seed(db, admin_email, "Admin", UserRole.admin, admin_password)
        _seed(db, operator_email, "Operator", UserRole.review_operator, operator_password)
    finally:
        db.close()


if __name__ == "__main__":
    main()
