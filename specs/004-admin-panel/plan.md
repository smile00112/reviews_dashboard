# Implementation Plan: Admin Panel with Authentication and RBAC

**Branch**: `feature/004-admin-panel` | **Date**: 2026-07-01 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/004-admin-panel/spec.md`

## Summary

Add an internal admin panel (`sqladmin`) to the existing FastAPI application, mounted
at `/admin`. Introduces a `User` model with bcrypt-hashed passwords and a role enum
(`admin` | `review_operator`). RBAC is enforced at the view layer via SQLAdmin's
`is_accessible` / `is_visible` and `can_create` / `can_edit` / `can_delete` hooks.
An additive Alembic migration extends `organizations` and `reviews` tables with admin-
facing columns. Existing API routes and scraper are untouched.

## Technical Context

**Language/Version**: Python 3.12+

**Primary Dependencies**:
- `sqladmin>=0.20` — admin panel sub-app for FastAPI + SQLAlchemy
- `passlib[bcrypt]>=1.7.4` — password hashing (bcrypt backend)
- `itsdangerous` — already transitive via starlette; explicit pin for clarity
- `starlette.middleware.sessions.SessionMiddleware` — cookie-based session store

**Storage**: PostgreSQL 16 (production), SQLite in-memory (tests via `conftest.py`)

**Testing**: pytest + `starlette.testclient.TestClient` (sync); in-memory SQLite; no
async test infra needed (ORM and admin are synchronous).

**Target Platform**: Linux/Docker (uvicorn). Windows dev supported.

**Project Type**: Web service sub-app — additive extension to existing FastAPI monolith.

**Performance Goals**: Internal tool; <5 s login round-trip on LAN; no concurrent-scale
target beyond a handful of simultaneous sessions.

**Constraints**:
- Admin MUST NOT touch `/api/*` routes or scraper logic.
- All secrets from env (`ADMIN_SECRET_KEY`, `SESSION_MAX_AGE`).
- Passwords: bcrypt only, plaintext never in code or logs.
- Each phase must leave `uvicorn app.main:app` startable and `alembic upgrade head`
  passable without errors.

**Scale/Scope**: ~10 internal users, ~tens of organizations (matches existing MVP scale).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. MVP Scope Discipline | ✅ PASS | Admin panel in-scope per constitution v1.2.0 |
| II. Read-Only Review Collection | ✅ PASS | Admin edits internal records only; no Yandex writes |
| III. Critical-Path Testing | ✅ PASS | Auth and RBAC tests in plan (Phases 7) |
| IV. Scraper Reliability | ✅ PASS | Scraper untouched |
| V. Simplicity (YAGNI) | ✅ PASS | sqladmin sub-app; no new service; no Celery |
| VI. Deterministic Local Analytics | ✅ PASS | Analytics untouched |
| VII. Admin Panel Security | ✅ PASS | bcrypt, session secret from env, per-view RBAC |

**Violations requiring Complexity Tracking**: None.

## Project Structure

### Documentation (this feature)

```text
specs/004-admin-panel/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   └── admin-auth.md    # Phase 1 output
└── tasks.md             # /speckit-tasks output (not created here)
```

### Source Code (repository root)

```text
apps/api/
  app/
    core/
      config.py            # + ADMIN_SECRET_KEY, SESSION_MAX_AGE (additive)
      security.py          # hash_password / verify_password (NEW)
    models/
      user.py              # User model + UserRole enum (NEW)
      organization.py      # + city, region, is_franchise columns (additive)
      review.py            # + status, is_paid, platform, paid_cost,
                           #   paid_marked_by_user_id, reply_text, reply_at,
                           #   replied_by_user_id columns (additive)
      enums.py             # + UserRole, ReviewStatus, ReviewPlatform (additive)
      __init__.py          # + User import
    admin/
      __init__.py          # setup_admin(app, engine) (NEW)
      auth.py              # AdminAuth(AuthenticationBackend) (NEW)
      base.py              # RoleGatedModelView base class (NEW)
      views.py             # UserAdmin, OrganizationAdmin, ReviewAdmin (NEW)
    scripts/
      seed_users.py        # create admin + operator users (NEW)
    main.py                # + SessionMiddleware + setup_admin() (additive)
  alembic/
    versions/
      0004_admin_rbac.py   # User table + additive org/review columns (NEW)
  tests/
    test_admin_auth.py     # auth success/failure/inactive/logout (NEW)
    test_admin_rbac.py     # RBAC per role per view (NEW)
```

**Structure Decision**: Single-project extension of existing `apps/api` monolith.
Admin sub-package `app/admin/`; CLI utilities in `app/scripts/`.

## Implementation Phases

### Phase 0 — Dependencies and Config

**Goal**: Install packages, add env vars to config, wire `SessionMiddleware`.

**Files**:
- `apps/api/pyproject.toml` — add `sqladmin>=0.20`, `passlib[bcrypt]>=1.7.4`
- `apps/api/app/core/config.py` — add `admin_secret_key: str`, `session_max_age: int = 43200`
- `apps/api/app/main.py` — `app.add_middleware(SessionMiddleware, secret_key=settings.admin_secret_key, max_age=settings.session_max_age)` after CORSMiddleware
- `.env.example` — `ADMIN_SECRET_KEY=change-me-in-production`

**Gate**: `uvicorn app.main:app` starts without errors.

### Phase 1 — Models and Migration

**Goal**: Add `User` model; extend `Organization` and `Review` with admin columns.

**Files**:
- `apps/api/app/models/enums.py` — add `UserRole(admin|review_operator)`, `ReviewStatus(new|in_progress|answered|escalated)`, `ReviewPlatform(yandex|google|gis2)`
- `apps/api/app/models/user.py` — `User` model (NEW)
- `apps/api/app/models/organization.py` — additive: `city`, `region`, `is_franchise`
- `apps/api/app/models/review.py` — additive: `status`, `is_paid`, `platform`, `paid_cost`, `paid_marked_by_user_id`, `reply_text`, `reply_at`, `replied_by_user_id`
- `apps/api/app/models/__init__.py` — export `User`
- `apps/api/app/core/security.py` — `hash_password()`, `verify_password()` using `passlib.hash.bcrypt`
- `apps/api/alembic/versions/0004_admin_rbac.py` — migration (NEW)
- `apps/api/alembic/env.py` — ensure `User` imported

**Gate**: `alembic upgrade head` and `alembic downgrade -1` both succeed on clean DB.

### Phase 2 — Mount Admin Panel

**Goal**: Initialize sqladmin, verify `/admin` is reachable.

**Files**:
- `apps/api/app/admin/__init__.py` — `setup_admin(app, engine)` returning `Admin` instance
- `apps/api/app/main.py` — call `setup_admin(app, engine)` after middleware

**Gate**: `GET /admin` → 200 or 302. `/api/health` still returns `{"status":"ok"}`.

### Phase 3 — Authentication

**Goal**: `AdminAuth` backend; login/logout/authenticate flow.

**Files**:
- `apps/api/app/admin/auth.py` — `AdminAuth(AuthenticationBackend)` with `login()` (verify email+bcrypt, write session), `logout()` (clear session), `authenticate()` (read session, check is_active)
- `apps/api/app/admin/__init__.py` — pass `authentication_backend=AdminAuth(secret_key)` to `Admin()`

**Gate**: Unauthenticated `/admin` → redirect `/admin/login`; correct creds → access; wrong creds → error on login page; inactive user → denied.

### Phase 4 — RBAC

**Goal**: Base view with role helper; per-view access flags.

**Files**:
- `apps/api/app/admin/base.py` — `RoleGatedModelView(ModelView)` with `_get_role(request)` helper reading `request.session.get("role")`
- `apps/api/app/admin/views.py` — `UserAdmin`, `OrganizationAdmin`, `ReviewAdmin`

**RBAC matrix**:

| View | admin | review_operator |
|------|-------|----------------|
| UserAdmin | accessible, full CRUD | `is_accessible=False`, `is_visible=False` |
| OrganizationAdmin | full CRUD | `can_create=False`, `can_edit=False`, `can_delete=False` |
| ReviewAdmin | full CRUD | `can_create=False`, `can_delete=False`; `can_edit=True` |

Review operator `form_columns` for ReviewAdmin excludes `paid_cost` and
`paid_marked_by_user_id` (those appear in admin form only).

**Gate**: Under review_operator session: no Users nav item; org list has no action
buttons; review edit saves `reply_text`/`status`/`is_paid` successfully.

### Phase 5 — View Configuration

**Goal**: Column lists, search, filters, sort for OrganizationAdmin and ReviewAdmin.

**OrganizationAdmin**: `column_list` = name, city, region, is_franchise, created_at;
search = name, city; filters = city, region, is_franchise; sort = name, city, created_at;
Russian `column_labels`.

**ReviewAdmin**: `column_list` = created_at, platform, organization_id, author_name,
rating, status, is_paid; default sort = created_at desc; search = author_name,
review_text; filters = platform, status, rating, is_paid; Russian `column_labels`.

**Gate**: Both views load with correct columns; filters return correct subsets.

### Phase 6 — Seed Script

**Goal**: Idempotent initial user creation.

**File**: `apps/api/app/scripts/seed_users.py` — reads `ADMIN_EMAIL` (default
`admin@example.com`), `ADMIN_PASSWORD`, `OPERATOR_EMAIL` (default
`operator@example.com`), `OPERATOR_PASSWORD` from env; skips insert if email exists.

**Gate**: Run twice → exactly 2 rows in users; both have hashed passwords.

### Phase 7 — Tests and Acceptance

**Files**:
- `apps/api/tests/test_admin_auth.py` — 5 scenarios: correct creds, wrong password,
  inactive user, unauthenticated redirect, logout clears session
- `apps/api/tests/test_admin_rbac.py` — 4 scenarios: operator no Users, operator no
  org edit, operator can edit review, admin full CRUD access

**Test approach**: `TestClient` + in-memory SQLite; create `User` rows with `hash_password`;
assert HTTP status codes and redirect `Location` headers.

**Gate**: `pytest apps/api/tests/test_admin_auth.py apps/api/tests/test_admin_rbac.py -v`
all green; full `pytest -v` remains green.

## Complexity Tracking

No constitution violations. No additional complexity required.
