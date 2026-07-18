---
name: run-local-stack
description: Use when the user asks to run/start/launch the project locally, restart the dev stack, or verify the app works on this machine ("запусти проект", "подними стек", "run locally", "start dev servers"). Also use before driving the app end-to-end (login, pages, API smoke).
---

# Run Local Stack (bare, no Docker)

On this machine the stack runs **bare**, not via `docker compose`:
Postgres :5432 (already running as a service), FastAPI :8000, Next.js :3000.
Python 3.13 is global (no venv); api deps and web `node_modules` are installed.

## Steps

1. **Check what's already up** (all three may be running — steps are idempotent):

   ```powershell
   Get-NetTCPConnection -State Listen | Where-Object { $_.LocalPort -in 3000,8000,5432 } |
     Select-Object LocalPort,OwningProcess | Sort-Object LocalPort -Unique
   ```

   - `5432` missing → start Windows service `postgresql-x64-18` (`Start-Service postgresql-x64-18`) before anything else. DB name: `yandex_reviews`.
   - `8000` / `3000` already listening → skip that server's start step.

2. **API** — MUST run as a background task (uvicorn blocks forever; a foreground shell call hangs). Claude: use the shell tool's `run_in_background: true`; humans: separate terminal.

   ```powershell
   Set-Location apps/api; python -m uvicorn app.main:app --port 8000
   ```

3. **Web** — same: background task only.

   ```powershell
   Set-Location apps/web; npm run dev
   ```

   Both `Set-Location` calls assume cwd = repo root; use absolute paths if unsure.

4. **Wait + smoke test** (poll until both respond, ~15–60 s for Next.js first compile):

   - `GET http://localhost:8000/health` → `200`
   - `GET http://localhost:3000` → `307` (auth-gated redirect to `/login` or `/overview` — success, not an error). NOTE: `Invoke-WebRequest` follows redirects by default and reports the final page's status — pass `-MaximumRedirection 0` to see the raw `307`, or accept `200` after following as equally fine.

## Drive it (verify like a user)

Panel is auth-gated (feature 004). Login via the web proxy (`:3000` rewrites `/api/*` to `:8000`), reuse the session cookie:

```powershell
$s = New-Object Microsoft.PowerShell.Commands.WebRequestSession
Invoke-WebRequest -Uri http://localhost:3000/api/auth/login -Method POST `
  -Body '{"email":"<admin email>","password":"<password>"}' `
  -ContentType 'application/json' -WebSession $s -UseBasicParsing
Invoke-WebRequest -Uri http://localhost:3000/overview -WebSession $s -UseBasicParsing
```

Expect `200` on both. Local admin credentials are NOT stored in the repo —
they live in Claude's project memory (`local-dev-access`) and come from
`python -m app.scripts.seed_users` (env `ADMIN_PASSWORD` / `OPERATOR_PASSWORD`;
seed is idempotent, skips existing emails).

Unauthenticated API reads work directly: `GET http://localhost:8000/api/organizations` → `200`.

## Common mistakes

| Mistake | Reality |
|---|---|
| Running `docker compose up` | This machine runs bare; compose isn't the local workflow here. |
| Treating `307` on `:3000` as failure | It's the auth redirect. Follow it or log in. |
| Looking for a venv to activate | None exists; global Python 3.13 has all deps + `uvicorn`. |
| Hitting `:8000` for login cookie | Cookie is same-origin; log in through `:3000` proxy. |
| Giving up when `:3000` slow to answer | First request compiles pages; poll up to ~60 s. |
