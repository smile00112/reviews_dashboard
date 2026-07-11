# Contract: Companies API (`/api/companies`)

Company = parent «Организация». Writes require `require_admin`; reads require an authenticated user (`get_current_user`). `review_operator` = read-only.

## GET /api/companies

`200` → `{ "items": [ CompanyResponse, ... ] }`. Each `CompanyResponse`:
```json
{ "id", "name", "is_active", "branch_count", "created_at", "updated_at" }
```

## POST /api/companies  (admin)

Request: `{ "name": "Coffee Co", "is_active": true }` (`is_active` optional, default true).
- `201` → `CompanyResponse`.
- `422` → empty/missing name.
- `401`/`403` → not signed in / not admin.

## GET /api/companies/{id}

`200` → `CompanyResponse`. `404` if unknown.

## PATCH /api/companies/{id}  (admin)

Request (partial): `{ "name"?, "is_active"? }`. `200` → updated `CompanyResponse`. `404` if unknown.

## DELETE /api/companies/{id}  (admin)

`204`. Sets `company_id = NULL` on child branches (FK ON DELETE SET NULL); does **not** delete branches or reviews. `404` if unknown.

## GET /api/companies/{id}/branches

Branches grouped by city.
`200` →
```json
{
  "company_id": "...",
  "groups": [
    { "city": "Москва", "branches": [ OrganizationResponse, ... ] },
    { "city": "Без города", "branches": [ ... ] }
  ]
}
```
Ordered by city (then branch name); NULL/empty city bucketed as "Без города" last. Branch objects are the existing `OrganizationResponse` (see organizations-ext.md).

## Test expectations

- admin: create → list shows it with `branch_count = 0`; add branch (via org create with `company_id`) → `branch_count = 1`; grouped endpoint returns it under its city.
- delete company with a branch → 204; branch still exists with `company_id = null`.
- review_operator: GET ok; POST/PATCH/DELETE → 403.
- unauthenticated: any → 401.
