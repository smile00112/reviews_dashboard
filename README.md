# Yandex Reviews MVP

Internal dashboard for collecting and displaying Yandex Maps organization reviews.

## Stack

- **API**: FastAPI, SQLAlchemy, Alembic, Playwright, BeautifulSoup, requests (Python)
- **Web**: Next.js, TypeScript, TailwindCSS
- **DB**: PostgreSQL 16

## Quick Start

```bash
cp .env.example .env
docker compose up --build
```

- Dashboard: http://localhost:3000
- API: http://localhost:8000
- Health: http://localhost:8000/health

## Local Development

### API

```bash
cd apps/api
pip install -e ".[dev]"
playwright install chromium
alembic upgrade head
uvicorn app.main:app --reload
```

### Web

```bash
cd apps/web
npm install
npm run dev
```

## Verification

```bash
cd apps/api && pytest -v
cd ../web && npm run lint && npm run test:e2e
```

See `specs/001-yandex-reviews-mvp/quickstart.md` for milestone validation steps.

## Operator Scripts

### Collecting reviews

```bash
cd apps/api
python -m scripts.scrape_reviews --org-id <uuid>              # one org, Yandex, settings cap (150)
python -m scripts.scrape_reviews --org-id <uuid> --all-reviews # one org, every review available
python -m scripts.scrape_reviews --all --platform 2gis        # every org, 2GIS
python -m scripts.scrape_reviews --all --limit 5 --dry-run    # print the plan; scrape nothing
python -m scripts.scrape_reviews --all --all-reviews --log-file
```

Collects reviews and persists them through `ScrapeService`, so each org gets its own
`ScrapeRun` row and the dedup contract, the org info refresh (name/rating/review
count/rating count/address) and the daily rating snapshot all apply. `--limit` and
`--offset` count **organizations**, not reviews.

`--platform` selects both the URL column and the default mode — `yandex` (default) →
`public_http` on `yandex_url`, `2gis` → `twogis_api` on `gis2_url`. `--mode` overrides
it; a mode belonging to the other platform is rejected at startup.

**Two limits worth knowing before reading the numbers:**

1. **`public_http` is the only Yandex mode that can use `PROXY_POOL`.** `public` and
   `operator_auth` drive Chromium, which cannot authenticate against a SOCKS5 proxy
   (`Browser does not support socks5 proxy authentication`). Unproxied, Yandex
   rate-limits with HTTP 429 and the run ends `needs_manual_action`. `--all-reviews`
   is therefore rejected for those scroll-based modes rather than silently ignored.
2. **Yandex serves at most ~600 reviews per org over `?page=N`** (12 pages; page 13
   returns HTTP 200 with no review blocks). An org displaying 1110 reviews yields 600
   even with `--all-reviews` — a platform ceiling, not a bug. The rest sit behind the
   SPA's infinite scroll, reachable only by the modes that cannot be proxied.

### Refreshing metrics only

```bash
cd apps/api
python -m scripts.scrape_metrics --platform both --dry-run   # preview
python -m scripts.scrape_metrics --platform yandex --limit 10
```

Follows each org's platform link and writes back **only** rating/review count — no
individual reviews, no `ScrapeRun`. Use `scrape_reviews` when you want the reviews.

### Google Sheets export

```bash
cd apps/api
python -m scripts.sync_ratings_to_sheet --dry-run   # preview the match/write plan
python -m scripts.sync_ratings_to_sheet             # append a dated rating/count column block
```

Appends a new 6-column block (rating + review count for Yandex/2GIS/Google) to the
operator's Google Sheet, matching rows by their latest Yandex Maps link. Requires a
service-account key at `apps/api/.local/credentials.json` (gitignored) shared as
Editor on the target sheet — see `GOOGLE_SHEETS_*` below.

```bash
cd apps/api
python -m scripts.sprav_login           # opens a visible browser; sign in by hand (password, QR, or 2FA)
python -m scripts.sprav_login --check   # verify the saved session without opening a browser
python -m scripts.sprav_orgs            # read the operator's org list from the cabinet, print as JSON
python -m scripts.sprav_orgs --out PATH --pretty
```

`sprav_login` opens Yandex Passport in a visible browser window; the operator signs
in by hand and the session is saved to the storage-state file (`--check` only
verifies an existing session, no browser). `sprav_orgs` reads the operator's
organization list from the Yandex Business cabinet (read-only) and prints it as
JSON to stdout, also writing it to a file.

**Two things to know before using these:**
1. **The web UI's "Login" button / `POST /api/scraper/yandex/login` does not
   currently work.** It calls `YandexAuthScraper.login`, whose hardcoded Passport
   selectors are stale — Yandex Passport now serves a React passwordless flow whose
   login field has no `name` attribute and a per-render generated id. It fails
   after a 30s timeout with a misleading "check credentials or 2FA" message.
   `python -m scripts.sprav_login` is the working route to a session.
   `YANDEX_OPERATOR_LOGIN`/`YANDEX_OPERATOR_PASSWORD` are consequently unused by
   this console login (it fills nothing).
2. **A saved session alone does not enable `operator_auth` scrapes.**
   `sprav_login` writes the storage-state file but touches no database, while
   `ScrapeService` gates `operator_auth` scrapes on the `scraper_sessions` DB row.
   After logging in, call `POST /api/scraper/yandex/session/check` (or the web
   UI's "Check Session") to mark the session valid.

## Environment Variables

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | PostgreSQL connection string |
| `YANDEX_OPERATOR_LOGIN` | Unused by the console login (`scripts.sprav_login` fills nothing); read only by the stale `YandexAuthScraper.login` API path |
| `YANDEX_OPERATOR_PASSWORD` | Unused by the console login; read only by the stale `YandexAuthScraper.login` API path |
| `YANDEX_STORAGE_STATE_PATH` | Playwright session file path |
| `SCRAPER_DEBUG_DIR` | Failed scrape debug artifacts |
| `NEXT_PUBLIC_API_URL` | API URL for web frontend |
| `SPRAV_COMPANIES_URL` | Yandex Business cabinet entry point read by `scripts.sprav_orgs` |
| `SPRAV_ORGS_OUTPUT_PATH` | Default output file for `scripts.sprav_orgs` (default `.local/sprav-orgs.json`) |
| `SPRAV_PAGE_TIMEOUT_MS` | Cabinet page-load timeout for `scripts.sprav_orgs` (default `90000`) |
| `GOOGLE_SHEETS_CREDENTIALS_PATH` | Service-account key path (default `.local/credentials.json`) |
| `GOOGLE_SHEETS_SPREADSHEET_ID` | Target spreadsheet ID for `sync_ratings_to_sheet` |
| `GOOGLE_SHEETS_WORKSHEET_GID` | Target worksheet `gid` within that spreadsheet |

## Features

- Organization board with manual scrape triggers
- Public and operator-auth Playwright scraping
- Browserless HTTP scraping (`public_http` mode) on a dedicated `/http-scraper` page —
  requests + pagination, bot-protection surfaces as `needs_manual_action` (no bypass)
- Review deduplication by content hash
- Global reviews feed with filters
- Scrape run history with debug artifact paths
- Rule-based review analytics: sentiment, problem categorization, rating↔sentiment mismatch
  (deterministic, local, no LLM) — `POST /api/organizations/{id}/analyze` (backfill),
  `GET /api/organizations/{id}/analytics` (per-org summary)

## Spec Kit Artifacts

- Specs: `specs/001-yandex-reviews-mvp/`, `specs/002-review-analytics/`, `specs/003-http-scraper/` (each has spec.md / plan.md / tasks.md)
- Constitution: `.specify/memory/constitution.md` (v1.1.0)
