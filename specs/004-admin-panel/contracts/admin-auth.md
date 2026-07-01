# Admin Auth Contract

**Feature**: 004-admin-panel | **Date**: 2026-07-01

## Overview

The admin panel is a server-rendered web UI mounted at `/admin`. It does not expose a
JSON API — authentication and access control operate via HTML form POST and cookie
sessions managed by `sqladmin`'s `AuthenticationBackend`.

## Endpoints (rendered by sqladmin)

### GET /admin/login

Returns the HTML login form.

**Access**: Public (no session required)

---

### POST /admin/login

Submits login credentials.

**Form fields**:
| Field | Type | Required |
|-------|------|----------|
| `username` | string (email) | Yes |
| `password` | string | Yes |

**Responses**:

| Condition | Result |
|-----------|--------|
| Correct credentials, active user | 302 → `/admin/` with session cookie set |
| Wrong password or unknown email | 200 re-render login form with error |
| Correct credentials, inactive user | 200 re-render login form with error |

**Session cookie**: `session` (signed by `ADMIN_SECRET_KEY`). Contains `{user_id: str, role: str}`.

---

### GET /admin/logout

Clears session and redirects to login.

**Access**: Authenticated session required

**Response**: 302 → `/admin/login`; `session` cookie cleared

---

### GET /admin/ (dashboard index)

Redirects to first accessible view.

**Access**: Authenticated session required; unauthenticated → 302 `/admin/login`

---

### GET /admin/user/list

User management list view.

**Access**: `admin` role only. `review_operator` → 403 or redirect

---

### GET /admin/organization/list

Organization list with search, filters, sort.

**Access**: `admin` and `review_operator`

**review_operator**: No Create/Edit/Delete action buttons rendered

---

### GET /admin/review/list

Review list with search, filters, sort.

**Access**: `admin` and `review_operator`

**review_operator**: Edit action available; Create and Delete buttons absent

---

### POST /admin/review/edit/{id}

Submit review edit form.

**Access**: `admin` → all fields; `review_operator` → `reply_text`, `status`, `is_paid` only.

Form submission of restricted fields by `review_operator` → those fields are excluded from
`form_columns` so they are never rendered or accepted.

## RBAC Summary

| Resource | admin | review_operator |
|----------|-------|----------------|
| GET /admin/user/* | ✅ | ❌ (hidden + forbidden) |
| GET /admin/organization/list | ✅ | ✅ read-only |
| POST /admin/organization/create | ✅ | ❌ |
| POST /admin/organization/edit/* | ✅ | ❌ |
| POST /admin/organization/delete/* | ✅ | ❌ |
| GET /admin/review/list | ✅ | ✅ |
| POST /admin/review/create | ✅ | ❌ |
| POST /admin/review/edit/* | ✅ | ✅ (limited fields) |
| POST /admin/review/delete/* | ✅ | ❌ |

## Security Notes

- Session secret from env; never hardcoded
- Session cookie is `HttpOnly` (set by Starlette's SessionMiddleware)
- `is_active=False` users are denied at `authenticate()` time, not just at login
- Passwords never logged or returned in any response
