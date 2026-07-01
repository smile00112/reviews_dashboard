# Research: Admin Panel with Authentication and RBAC

**Feature**: 004-admin-panel | **Date**: 2026-07-01

## Decision 1: Admin Framework

**Decision**: `sqladmin` (not `starlette-admin`)

**Rationale**: sqladmin is the de-facto standard for FastAPI + SQLAlchemy; mounts as
a sub-app on the existing `FastAPI()` instance; uses the same sync `engine` already in
`core/database.py`; ships `AuthenticationBackend` and per-view `is_accessible` /
`is_visible` / `can_create` / `can_edit` / `can_delete` — sufficient for 2-role RBAC.
No new service or worker required (YAGNI, Principle V).

**Alternatives considered**:
- `starlette-admin` — richer per-action rights (`can_edit(request)`) but more setup;
  deferred as a future upgrade if per-record RBAC is needed.
- Custom admin dashboard with Next.js — high effort, out of scope for this iteration.

## Decision 2: Password Hashing

**Decision**: `passlib[bcrypt]` with `CryptContext(schemes=["bcrypt"])`

**Rationale**: bcrypt is the industry standard for slow-hash password storage; passlib
provides a clean API (`hash`, `verify`) with automatic salt generation; no external
service or GPU risk.

**Alternatives considered**:
- `argon2-cffi` — newer, arguably stronger, but adds a C extension; bcrypt is fully
  sufficient for internal tooling and is already widely supported.
- `hashlib.sha256` — fast hash, NOT suitable for passwords (vulnerable to brute-force).

## Decision 3: Session Management

**Decision**: `starlette.middleware.sessions.SessionMiddleware` with signed cookies

**Rationale**: Starlette's built-in session middleware is already available as a
transitive FastAPI dependency; stores session data as a signed, encrypted cookie using
`itsdangerous`; no server-side session store needed for <10 users.

**Secret handling**: `ADMIN_SECRET_KEY` env var, validated at startup by pydantic-settings
(missing → `ValidationError`, app won't start).

**Session lifetime**: `SESSION_MAX_AGE=43200` seconds (12 h), configurable via env.

**Alternatives considered**:
- Redis-backed server-side sessions — unnecessary overhead for internal tooling.
- JWT in Authorization header — would require custom JS in the admin UI; SQLAdmin
  expects cookie-based sessions.

## Decision 4: RBAC Mechanism

**Decision**: Override `is_accessible`/`is_visible`/`can_create`/`can_edit`/`can_delete`
on each `ModelView` subclass; read role from `request.session["role"]`.

**Rationale**: SQLAdmin provides these hooks exactly for this purpose; no middleware
interception needed; role is stored in the signed session cookie set at login.

**Operator-editable review fields** (CL-002): `reply_text`, `status`, `is_paid`.
Fields `paid_cost` and `paid_marked_by_user_id` are excluded from `form_columns` for
the operator role to prevent accidental edits.

**Implementation**: `RoleGatedModelView(ModelView)` base class provides `_get_role(request)`
helper; subclasses branch on `role == "admin"` vs `"review_operator"`.

## Decision 5: Migration Strategy

**Decision**: Single migration `0004_admin_rbac.py` that:
1. Creates `users` table with `user_role_enum` Postgres type.
2. Adds nullable columns to `organizations`: `city TEXT`, `region TEXT`, `is_franchise BOOLEAN DEFAULT FALSE`.
3. Adds nullable columns to `reviews`: `status review_status_enum`, `is_paid BOOLEAN DEFAULT FALSE`, `platform review_platform_enum`, `paid_cost INTEGER`, `paid_marked_by_user_id UUID FK users`, `reply_text TEXT`, `reply_at TIMESTAMPTZ`, `replied_by_user_id UUID FK users`.

**Rationale**: All new columns are nullable or have safe defaults — existing rows are
valid after migration with no data loss. Enum values added as new Postgres types to
avoid `ALTER TYPE` on shared existing types (which requires careful transaction handling,
as seen in migration 0003).

**Downgrade**: `drop_table("users")` + `drop_column` for each additive column + `drop_type`
for new enums.

## Decision 6: Test Strategy

**Decision**: Sync `TestClient` + in-memory SQLite (matching existing `conftest.py`
pattern). Two new test files: `test_admin_auth.py` and `test_admin_rbac.py`.

**Rationale**: Existing test suite uses this pattern; SQLite supports all ORM models;
sqladmin's `TestClient`-accessible routes allow HTTP-level assertions without browser
automation.

**Known limitation**: SQLite uses `CHECK` constraints instead of Postgres `ENUM` types;
Enum columns use `VARCHAR` in SQLite. This is consistent with existing model pattern
(`values_callable=lambda x: [e.value for e in x]`).
