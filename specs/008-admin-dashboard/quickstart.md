# Quickstart / Validation: Admin Control Panel

Prerequisites: repo on `feature/008-admin-dashboard`, `.env` with `DATABASE_URL` and `ADMIN_SECRET_KEY` set, Postgres running.

## 1. Backend up-to-date

```bash
cd apps/api
pip install -e ".[dev]"
alembic upgrade head            # applies 0008_companies
pytest -v                       # all green incl. unchanged dedup/normalization tests
python -m app.scripts.seed_users  # seed at least one admin (bcrypt); creds via env/CLI
uvicorn app.main:app --reload
```

Expected: `/health` 200; `companies` table exists; `organizations.company_id` column exists.

## 2. Frontend up

```bash
cd apps/web
npm install
npm run lint
npm run dev                     # http://localhost:3000
```

## 3. Auth gate (User Story 1 / SC-001)

- Open `http://localhost:3000/companies` while signed out → redirected to `/login`.
- Submit wrong credentials → stays on `/login` with an error, no session.
- Submit the seeded admin credentials → lands in the dashboard shell (dark prototype style).
- Click sign out → `/companies` redirects to `/login` again.

## 4. Create a Company (User Story 2 / SC-002)

- In Organizations (Организации), create company "Coffee Co" → appears in list with 0 branches.
- Open it → detail view shows empty branch list grouped by city.

## 5. Add Branches grouped by city (User Story 3 / SC-003)

- In "Coffee Co", add branch "Тверская, 17", city Москва, with a Yandex maps URL → appears under a "Москва" group.
- Add branch "Невский, 88", city СПб → a second "СПб" group appears.
- Add another Москва branch → grouped under the existing "Москва" heading (no duplicate group).
- Edit a branch's city → it moves to the correct group.

## 6. Collection unchanged (SC-005 / SC-006)

- Trigger collection on a new branch via the existing control (`POST /api/organizations/{id}/scrape`).
- Reviews are collected and deduplicated exactly as before (branch == existing org row). Re-scrape does not duplicate reviews.

## 7. Read-only role (User Story 4 / SC-004)

- Sign in as a `review_operator` user → Organizations visible, but no create/edit/delete controls.
- Direct write attempt (e.g. `POST /api/companies` with that session) → `403`.

## Contracts referenced

- Auth: [contracts/auth-api.md](./contracts/auth-api.md)
- Companies: [contracts/companies-api.md](./contracts/companies-api.md)
- Organizations (branch) extensions: [contracts/organizations-ext.md](./contracts/organizations-ext.md)
- Data model: [data-model.md](./data-model.md)
