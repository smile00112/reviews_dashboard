# Data Model: Admin Panel with Authentication and RBAC

**Feature**: 004-admin-panel | **Date**: 2026-07-01

## New Entity: User

**Table**: `users`

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | UUID | PK, default `uuid4()` | |
| `name` | TEXT | NOT NULL | Display name |
| `email` | TEXT | NOT NULL, UNIQUE | Login identifier |
| `role` | `user_role_enum` | NOT NULL | `admin` or `review_operator` |
| `is_active` | BOOLEAN | NOT NULL, DEFAULT TRUE | Inactive → login denied |
| `password_hash` | TEXT | NOT NULL | bcrypt hash, never plaintext |
| `default_location_id` | UUID | FK `organizations.id`, nullable | Optional home org |
| `avatar_initials` | TEXT | nullable | Derived display; e.g., "АИ" |
| `created_at` | TIMESTAMPTZ | NOT NULL, server default `now()` | |

**New Postgres enum**: `user_role_enum` VALUES (`admin`, `review_operator`)

**Unique constraint**: `uq_user_email` on `email`

**Relationships**:
- `default_location_id` → `organizations.id` ON DELETE SET NULL
- `reviews.replied_by_user_id` → `users.id` ON DELETE SET NULL
- `reviews.paid_marked_by_user_id` → `users.id` ON DELETE SET NULL

---

## Extended Entity: Organization (additive columns)

**Table**: `organizations` — 3 new nullable columns added

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `city` | TEXT | nullable | City of the location |
| `region` | TEXT | nullable | Region/oblast |
| `is_franchise` | BOOLEAN | NOT NULL, DEFAULT FALSE | Franchise vs own branch |

---

## Extended Entity: Review (additive columns)

**Table**: `reviews` — 9 new columns added

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `status` | `review_status_enum` | nullable, DEFAULT `new` | Triage workflow status |
| `is_paid` | BOOLEAN | NOT NULL, DEFAULT FALSE | Suspected purchased review |
| `platform` | `review_platform_enum` | nullable, DEFAULT `yandex` | Source platform |
| `paid_cost` | INTEGER | nullable | Estimated cost in ₽ (admin only) |
| `paid_marked_by_user_id` | UUID | FK `users.id`, nullable | Admin who marked paid |
| `reply_text` | TEXT | nullable | Operator's drafted reply |
| `reply_at` | TIMESTAMPTZ | nullable | When reply was set |
| `replied_by_user_id` | UUID | FK `users.id`, nullable | Operator who replied |

**New Postgres enums**:
- `review_status_enum` VALUES (`new`, `in_progress`, `answered`, `escalated`)
- `review_platform_enum` VALUES (`yandex`, `google`, `gis2`)

---

## State Transitions

### Review.status

```
new → in_progress → answered
      in_progress → escalated
      escalated   → in_progress
```

Only `admin` and `review_operator` can change status. No automated state machine —
all transitions are manual edits in the admin panel.

---

## Session State (cookie, not persisted)

| Key | Type | Set by | Cleared by |
|-----|------|--------|-----------|
| `user_id` | str (UUID) | `AdminAuth.login()` | `AdminAuth.logout()` |
| `role` | str | `AdminAuth.login()` | `AdminAuth.logout()` |

No server-side session table. If `ADMIN_SECRET_KEY` rotates, all sessions are
invalidated.

---

## Migration Dependency Chain

```
0001_initial → 0002_review_analysis → 0003_public_http_mode → 0004_admin_rbac
```

`0004_admin_rbac.py`:
- `revises = "0003_public_http_mode"`
- Creates `users` table and `user_role_enum`
- Creates `review_status_enum` and `review_platform_enum`
- Adds columns to `organizations` and `reviews`
- Downgrade removes all of the above in reverse order
