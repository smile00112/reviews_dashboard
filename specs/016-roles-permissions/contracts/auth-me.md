# Contract: Auth / current user

## GET /api/auth/me

Returns the signed-in user with role object and effective permission set so the frontend can
mirror access decisions (FR-019). Requires a valid session (else 401).

**200 Response**

```json
{
  "id": "uuid",
  "name": "Иван Оператор",
  "email": "operator@example.com",
  "role": {
    "id": "uuid",
    "slug": "call_center",
    "name": "Колл-центр",
    "is_system": false
  },
  "permissions": [
    "page:overview",
    "page:ratings",
    "page:reviews",
    "action:review.edit_status"
  ]
}
```

- For an `admin` user, `permissions` contains the **entire catalog** (all 21 keys) and
  `role.is_system == true`.
- `permissions` is the deny-by-default effective set; absence of a key = not allowed.

**401** — no valid session: `{"detail": "Not authenticated"}`.

### Backwards compatibility

`role` changes from a bare enum string (`"admin"`) to an object. `UserResponse.role` (used by
`/login` and `/me`) is updated accordingly; `permissions[]` is added. The web `CurrentUser`
type and `ROLE_LABEL` map are updated to read `role.name` / `role.slug`.

## POST /api/auth/login

Unchanged request (`email`, `password`). Response body is the same shape as `/me` (role
object + permissions). Sets the session cookie. `401` invalid credentials, `403` inactive.

## POST /api/auth/logout

Unchanged — clears session, 204.
