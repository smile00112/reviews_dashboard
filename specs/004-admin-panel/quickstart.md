# Quickstart: Admin Panel Validation

**Feature**: 004-admin-panel | **Date**: 2026-07-01

## Prerequisites

- Docker Compose running (`docker compose up --build`)
- Or: local Postgres + `alembic upgrade head` in `apps/api/`
- `.env` contains `ADMIN_SECRET_KEY`, `ADMIN_PASSWORD`, `OPERATOR_PASSWORD`

## Phase-by-Phase Validation

### Phase 0 — Config

```bash
cd apps/api
uvicorn app.main:app --reload
# Expected: server starts; no ImportError; /health returns {"status":"ok"}
```

### Phase 1 — Migration

```bash
cd apps/api
alembic upgrade head
# Expected: migration 0004_admin_rbac applies without errors

alembic downgrade -1
# Expected: rolls back 0004 cleanly

alembic upgrade head
# Re-apply for further phases
```

### Phase 2 — Admin Reachable

```
GET http://localhost:8000/admin
# Expected: 302 → /admin/login  OR  200 login page HTML
```

### Phase 3 — Authentication

1. Open `http://localhost:8000/admin/login`
2. Submit wrong password → stays on login page, error shown
3. Submit valid admin credentials → redirected to `/admin/`
4. Click Logout → redirected to `/admin/login`
5. Create inactive user in DB, attempt login → denied

### Phase 4 — RBAC (manual)

1. Log in as `review_operator`
2. Verify: "Users" section absent from sidebar
3. Navigate to Organizations → no Create / Edit / Delete buttons
4. Navigate to Reviews → Edit button present, no Create or Delete

### Phase 5 — Filters and Search

1. Log in as admin
2. Open Organizations → type in search box → results filter
3. Apply is_franchise filter → only franchise orgs shown
4. Open Reviews → filter by `status=new` → verify subset

### Phase 6 — Seed Script

```bash
cd apps/api
ADMIN_EMAIL=admin@example.com ADMIN_PASSWORD=secret123 \
OPERATOR_EMAIL=op@example.com OPERATOR_PASSWORD=pass456 \
python -m app.scripts.seed_users
# Expected: "Created admin admin@example.com" + "Created operator op@example.com"

# Run again — should be idempotent:
python -m app.scripts.seed_users
# Expected: "Skipped admin@example.com (exists)" + "Skipped op@example.com (exists)"
```

### Phase 7 — Automated Tests

```bash
cd apps/api
pytest tests/test_admin_auth.py tests/test_admin_rbac.py -v
# Expected: all tests PASSED

pytest -v
# Expected: full suite still green (no regressions)
```

## Acceptance Checklist (§6 of admin_panel_plan.md)

- [X] `/admin` requires login; email+password works; logout clears session
- [X] Passwords stored as hashes; secret from env
- [X] `admin` role: full CRUD on organizations, reviews, users
- [X] `review_operator`: sees/edits reviews; read-only orgs; Users hidden; no create/delete reviews
- [X] Organizations and Reviews show data with search, filters, sort
- [X] Alembic migration applies on clean DB without errors
- [X] Seed script creates admin and operator (idempotent)
- [X] Tests green
- [X] `uvicorn` starts; existing API/scraper unchanged
