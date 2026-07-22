# Quickstart / Validation: Roles & Permissions (feature 016)

Prerequisites: local stack per README (`docker compose up --build`, or native Postgres +
`uvicorn` + `npm run dev`). Apply migrations: `alembic upgrade head` (brings in `0024`).

## 1. Migration & continuity

```bash
cd apps/api && alembic upgrade head
pytest tests/test_role_migration.py -v
```

Expected: `roles` seeded with `admin`, `call_center`, `manager`; every existing user has a
`role_id`; a pre-existing `admin` user maps to the admin role, a `review_operator` to
`call_center`; no user is left role-less.

## 2. Backend enforcement (source of truth)

```bash
pytest tests/test_rbac_permissions.py tests/test_roles_api.py tests/test_auth_me_permissions.py -v
```

Validate:
- A user whose role lacks `action:scrape.run` gets **403** POSTing a scrape trigger; an admin
  gets **202**. Unauthenticated → **401**.
- A user whose role lacks `action:review.edit_status` gets **403** on the review PATCH.
- `GET /api/auth/me` returns the correct `permissions[]` per role; admin returns the full
  catalog.
- Role CRUD guards: deleting `admin` → 403; renaming `admin` → 403; editing admin grants →
  403; deleting an in-use role → 409; duplicate/blank name → 409/422; unknown permission key
  in a grant → 422.

## 3. Full API + web gates

```bash
cd apps/api && pytest -v
cd ../web && npm run lint && npm run test:e2e   # includes tests/roles.spec.ts
```

`roles.spec.ts` scenario (User Story 1+2):
1. Sign in as admin, open **Настройки → Роли и доступ**.
2. Grant the `manager` role `page:reviews` but not `action:review.edit_status`; save.
3. Sign in as a manager user: navigation shows **Отзывы**; opening a review shows **no**
   status-editing controls; a direct status-change request is refused (403).
4. Back as admin, grant `action:review.edit_status`; the manager now sees and can use the
   status control.

## 4. Manual smoke (optional)

- As admin: create a role "Аналитик" with only `page:overview` + `page:ratings`; assign a
  user; confirm that user's sidebar shows only those two pages and every other page URL
  redirects/404s; confirm `/settings/roles` is hidden for that user and the roles API returns
  403 for them.
- Confirm the sqladmin panel at `/admin` still admits only users whose role slug is `admin`.
- Confirm the permission catalog (`GET /api/roles/catalog`) contains **no** reply-to-provider
  permission.

## Success = all of

- `pytest -v` green (api), `npm run lint && npm run test:e2e` green (web) — the README
  verification gate.
- The new tests in steps 1–3 pass.
- Existing accounts keep equivalent access (step 1).
