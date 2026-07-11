# Contract: Auth API (`/api/auth`)

Session-cookie auth reusing feature-004 `users`/bcrypt/`SessionMiddleware`. No JWT.

## POST /api/auth/login

Request:
```json
{ "email": "admin@example.com", "password": "secret" }
```
Behavior: look up active user by email; `verify_password(password, user.password_hash)`. On success set `request.session["user_id"] = str(user.id)` and `request.session["role"] = user.role`.

Responses:
- `200` → `{ "id", "name", "email", "role" }` (no password fields).
- `401` → `{ "detail": "Invalid credentials" }` (same message for unknown email or wrong password; no session set).
- `403` → inactive user (`is_active == false`).

## POST /api/auth/logout

Clears the session. `204` No Content. Idempotent (also `204` when not signed in).

## GET /api/auth/me

Reads the session. 
- `200` → current user `{ "id", "name", "email", "role" }`.
- `401` → `{ "detail": "Not authenticated" }` when no valid session.

## Dependencies (server-side)

- `get_current_user(request) -> User`: loads user from `request.session["user_id"]`; raises `401` if missing/invalid. Used by `GET /me` and to protect write routes.
- `require_admin(user = Depends(get_current_user)) -> User`: raises `403` unless `user.role == "admin"`. Used by mutating company/branch routes. `review_operator` may read but not write.

## Test expectations

- Valid login → 200 + session cookie; subsequent `/me` → 200.
- Wrong password / unknown email → 401, no session.
- `/me` without session → 401.
- Logout → 204; `/me` afterwards → 401.
