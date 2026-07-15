# Yandex Sprav cabinet scraper (organization list) — design

**Date:** 2026-07-15
**Status:** approved (brainstorming), pending implementation plan

## Goal

Read the **list of organizations the operator manages** from the Yandex Business
cabinet (`https://yandex.ru/sprav/`) using the Playwright storage-state session the
project already produces for `operator_auth` mode. Driven from the console only:

- a command to authorize (test the login path end-to-end), and
- a command to read the organization list and emit it as JSON.

Nothing is written to the database in this iteration. Reviews from the cabinet are
explicitly out of scope for the first version.

## Context

### Why the cabinet is reachable with the session we already have

`sprav` sits behind the same Yandex Passport SSO as Yandex Maps. Login produces
domain-wide cookies on `.yandex.ru` — principally `Session_id` and `sessionid2`
(both HttpOnly; `sessionid2` is HTTPS-only) — and those authorize every Yandex
service, cabinet included. `YandexAuthScraper.login` already saves exactly these
into `settings.yandex_storage_state_path` via `context.storage_state(path=...)`.

Consequence: **no new authorization mechanism is needed and no second session file
is introduced.** The sprav scraper reuses `settings.yandex_storage_state_path`.

### Why Playwright, not raw HTTP

A browserless `httpx` client with the extracted cookies is possible, but the cabinet
is a heavy SPA: any internal API call needs a CSRF token (`x-csrf-token`/`sk`) that
is issued in the page payload, not in a cookie, and must be scraped first. Driving a
real Playwright context makes cookies, CSRF, headers, and JS init the browser's
problem. This is the "Variant A" chosen in brainstorming.

### Existing patterns reused

- `app/scraper/yandex_auth.py` — `YandexAuthScraper.login` / `check_session`, the
  storage-state lifecycle.
- `app/scraper/markers.py` — shared bot/captcha markers.
- `app/scraper/debug_artifacts.py` — `save_debug_artifacts(page, prefix)`.
- `app/scraper/parser.py` — the pure-parser precedent (`parse_reviews_from_html`):
  I/O in the scraper class, parsing in a pure, unit-tested function.
- `scripts/scrape_metrics.py`, `scripts/import_companies_csv.py` — the operator CLI
  precedent (`python -m scripts.<name>`, argparse).

## Constraints

- **Read-only.** The cabinet exposes editing of organizations and replying to
  reviews. This feature performs **GET/read only** — no writes, ever. Constitution
  hard rule: never publish, edit, or delete on Yandex.
- **No captcha bypass.** A captcha wall or a redirect to `passport.yandex.ru`
  surfaces as `needs_manual_action` with debug artifacts saved. No silent retries.
- **Credentials stay in env.** `YANDEX_OPERATOR_LOGIN` / `YANDEX_OPERATOR_PASSWORD`;
  storage-state stays under gitignored `.local/`, never logged, never printed.

## Components

### 1. `app/scraper/yandex_sprav.py` — `YandexSpravScraper`

I/O layer. One public method:

```python
def list_organizations(self, storage_state_path: str) -> SpravListResult
```

Flow:
1. Missing/empty storage-state file → `needs_manual_action`, `error_code =
   "missing_session"`. No browser launched.
2. `browser.new_context(storage_state=..., locale=..., extra_http_headers=...)`
   reusing `YandexPublicScraper.LOCALE` / `EXTRA_HTTP_HEADERS`.
3. Register a `page.on("response")` handler to capture the companies-list XHR
   before navigating, then go to the cabinet companies page.
4. Detect challenge: URL now on `passport.yandex.ru`, or a marker from
   `scraper/markers.py` present in the HTML → `needs_manual_action`,
   `error_code = "access_challenge"`, `save_debug_artifacts(page, "sprav-list")`.
5. Hand the captured JSON to `parse_sprav_orgs`.

Network interception is preferred over DOM scraping: the cabinet is an SPA whose
markup is volatile, whereas the JSON it fetches is structured and stable enough to
snapshot as a fixture.

### 2. `parse_sprav_orgs(payload: dict) -> list[SpravOrg]` — pure parser

Same module, no I/O, no DB, independently testable.

`SpravOrg` dataclass:

| field           | type          | notes                                   |
|-----------------|---------------|-----------------------------------------|
| `sprav_id`      | `str`         | cabinet's own organization id           |
| `name`          | `str`         |                                         |
| `address`       | `str \| None` |                                         |
| `rating`        | `float \| None` |                                       |
| `reviews_count` | `int \| None` |                                         |
| `url`           | `str \| None` | public Yandex Maps link, when available  |

Degrades safely: unknown/empty/garbage payload → `[]`, never raises. Missing
per-field values → `None`.

`SpravListResult` dataclass: `organizations: list[SpravOrg]`,
`needs_manual_action: bool`, `error_code: str | None`, `error_message: str | None`,
`debug_screenshot`/`debug_html` — mirroring the `ScrapeResult` contract so the
failure semantics read the same as every other scraper.

### 3. `scripts/sprav_login.py` — authorization test command

```
python -m scripts.sprav_login [--check] [--headed]
```

Thin wrapper over `YandexAuthScraper`, **no database** — it tests the login path in
isolation.

- default: `login(login, password, path)` with env credentials, headless. Prints the
  resulting `SessionStatus` + message.
- `--check`: skip login, run `check_session(path)` against the existing storage-state
  and print the status.
- `--headed`: escape hatch. Launches a visible browser so the operator can complete
  2FA/captcha by hand; the script waits for login to complete and then saves the
  storage-state. Needed because a headless auto-login **cannot** pass 2FA or a
  captcha — on such an account the default path honestly returns
  `needs_manual_action` and saves nothing.
- Exit code `0` only on `SessionStatus.valid`.

Supporting `--headed` requires threading a `headless: bool = True` parameter through
`YandexAuthScraper.login`. Default preserves today's behaviour, so
`ScrapeService.login_operator` and the API path are unaffected.

### 4. `scripts/sprav_orgs.py` — organization list command

```
python -m scripts.sprav_orgs [--out PATH] [--pretty]
```

- Runs `YandexSpravScraper().list_organizations(settings.yandex_storage_state_path)`.
- Prints the organizations as JSON to stdout; also writes them to `--out`
  (default `settings.sprav_orgs_output_path` = `.local/sprav-orgs.json`).
- `--pretty` → indented JSON.
- `needs_manual_action` → print the reason plus "run `python -m scripts.sprav_login`
  first", exit code `2`. Other errors → exit code `1`.
- Only the organization list goes to stdout, so the command stays pipeable to `jq`;
  progress/diagnostics go to stderr.

### 5. `core/config.py`

Add:

- `sprav_orgs_output_path: str = ".local/sprav-orgs.json"`
- `sprav_companies_url: str = "https://yandex.ru/sprav/"` — the entry point, kept in
  settings so a cabinet URL change is a config edit, not a code edit.

## Data flow

```
sprav_login  → YandexAuthScraper.login (headless by default, env creds)
             → .local/yandex-storage-state.json

sprav_orgs   → YandexSpravScraper.list_organizations
                 → Playwright context(storage_state) → capture companies XHR
                 → parse_sprav_orgs(json) → list[SpravOrg]
                 → stdout (JSON) + .local/sprav-orgs.json
```

## Error handling

| Condition                            | Outcome                                                |
|--------------------------------------|--------------------------------------------------------|
| storage-state missing/empty          | `needs_manual_action`, `missing_session`, no browser    |
| redirect to passport / captcha wall  | `needs_manual_action`, `access_challenge` + artifacts   |
| companies XHR never seen             | `error_code = "sprav_list_not_found"` + artifacts       |
| unexpected/empty JSON                | parser returns `[]` (no raise)                          |
| network/timeout/other exception      | `error_code = "sprav_scrape_error"`, message attached   |

## Testing

Critical path here is the parser — it is the only pure, deterministic unit.

- `tests/test_sprav_parser.py`:
  - happy path: real captured fixture → expected `SpravOrg` list.
  - empty payload / garbage payload / missing fields → `[]` or `None` fields, no raise.
- No live-network test (constitution: scrapers are not exercised against real sites
  in tests). The Playwright I/O layer is not mocked.

## Implementation note — endpoint discovery comes first

The exact companies-list URL and JSON shape are **not** assumed by this design. Task
one of implementation is to discover them live: open the cabinet in a headed browser
with a valid storage-state, capture the companies XHR, and save the response as the
test fixture under `tests/fixtures/`. The parser is then written against the real
payload, not a guess. If the cabinet turns out to server-render the list instead of
fetching it, the fallback is a DOM parse of the same page — the pure-parser boundary
is unchanged, only its input type is.

## Out of scope

- Reviews from the cabinet (planned as a follow-up once the list works).
- Any write action in the cabinet (permanently out — constitution).
- Persisting cabinet organizations to the `organizations` table / mapping them to
  existing rows.
- A new `ScrapeMode`, an API endpoint, or a web page. Console only for now.
- Captcha bypass.
