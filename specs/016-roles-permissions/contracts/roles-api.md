# Contract: Roles API

All endpoints require the `action:roles.manage` permission (→ `admin` and any role granted
it). Unauthenticated → **401**; authenticated without the permission → **403**.

Base prefix: `/api/roles`.

## GET /api/roles/catalog

The static permission catalog for the matrix UI. Read-only.

**200**
```json
{
  "pages": [
    { "key": "page:overview", "label": "Обзор сети" },
    { "key": "page:reviews", "label": "Отзывы" }
  ],
  "actions": [
    { "key": "action:scrape.run", "label": "Запуск сбора" },
    { "key": "action:review.edit_status", "label": "Изменение статуса отзыва" }
  ]
}
```

## GET /api/roles

List all roles with their grants and assigned-user count.

**200**
```json
[
  {
    "id": "uuid",
    "slug": "admin",
    "name": "Администратор",
    "is_system": true,
    "description": null,
    "permissions": ["*"],
    "user_count": 1
  },
  {
    "id": "uuid",
    "slug": "call_center",
    "name": "Колл-центр",
    "is_system": false,
    "description": null,
    "permissions": ["page:overview", "page:ratings", "page:reviews", "action:review.edit_status"],
    "user_count": 2
  }
]
```

- The `admin` role reports `permissions: ["*"]` (sentinel meaning "all") — the UI renders its
  row as fully checked and disabled.

## POST /api/roles

Create a role.

**Request**
```json
{ "name": "Аналитик", "description": "read-only analytics", "permissions": ["page:overview", "page:ratings"] }
```

- `name`: required, non-empty, unique (case-insensitive) → **409** on duplicate, **422** on blank.
- `slug`: auto-derived from `name` (transliterated/normalized), unique; **409** on collision.
- `permissions`: optional; every entry must be in the catalog → **422** on unknown key.

**201** → the created role object (same shape as list item).

## PATCH /api/roles/{id}

Rename / edit description. **Cannot** target the `is_system` role → **403**.

**Request** `{ "name": "...", "description": "..." }` (partial). Same name validation as create.

**200** → updated role. **404** unknown id.

## PUT /api/roles/{id}/permissions

Replace the full grant set for a role. **Cannot** target the `is_system` role → **403**.

**Request** `{ "permissions": ["page:overview", "action:scrape.run"] }`

- Full replace (not a delta). Unknown key → **422**.

**200** → updated role with new `permissions`.

## DELETE /api/roles/{id}

Delete a role.

- `is_system` role → **403** (cannot delete admin).
- Role assigned to ≥1 user → **409** `{"detail": "role in use"}` (FR-004).
- Otherwise cascades its `role_permissions` rows.

**204** on success. **404** unknown id.

## Enforcement notes

- Every mutating route across the app is guarded by its specific `require_permission(...)`
  (see data-model.md route map), returning **403** on deny regardless of what the UI shows
  (FR-015/FR-018). The Roles API above is itself guarded by `action:roles.manage`.
