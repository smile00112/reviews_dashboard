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
3. Navigate to the cabinet; `/sprav/` redirects to `/sprav/companies`.
4. Detect challenge: URL now on `passport.yandex.ru`, or a marker from
   `scraper/markers.py` present in the HTML → `needs_manual_action`,
   `error_code = "access_challenge"`, `save_debug_artifacts(page, "sprav-list")`.
5. Hand `page.content()` to `extract_preload_data`, then to `parse_sprav_orgs`.

### Confirmed cabinet payload (Task 2, live, 2026-07-15)

The first cut of this design assumed the list arrives as an XHR that we would
capture via network interception. **It does not.** With a valid storage-state,
`https://yandex.ru/sprav/` redirects to `/sprav/companies` and inlines its state
into the page:

```
window.__PRELOAD_DATA = { … "initialState": { "companiesList": {
    "listCompanies": [ … ], "total": 2, "page": 1, "limit": 10 } } }
```

The eight JSON responses the page does fetch are ads, mail counters, metrics and
a survey — plus `/sprav/api/companies/get-companies-adv`, which returns only
per-chain advertising flags. None carries the list. So the parser reads the HTML,
and the design's stated fallback ("if the cabinet server-renders it") is the path
taken.

Two further findings that reshaped the data model:

- **No rating or review data exists in the cabinet's company pages.** The string
  `rating` occurs 0 times in the 64 KB companies preload and 0 times in the
  630 KB chain page. `rating`/`reviews_count` are therefore **dropped** from
  `SpravOrg` — unobtainable here, and still the Maps scrapers' job.
- **The records are chains, not branches.** `type: "chain"`, `total: 2`, with
  `chain.branchCount` 357 and 2. Individual branches live a level deeper at
  `/sprav/chain/{tycoon_id}` (`companyList.pager.total` = 209 for the big chain).
  Listing branches is out of scope for this feature.

Field mapping, verified against the live payload:

| `SpravOrg` field    | Source in `listCompanies[i]`     | Note                                    |
|---------------------|----------------------------------|-----------------------------------------|
| `sprav_id`          | `permanent_id`                   | equals `id`; the Yandex Maps permalink  |
| `name`              | `displayName`                    |                                         |
| `address`           | `address.formatted.value`        | `formatted` is a dict, **not** a string |
| `url`               | `urls[type == "main"].value`     | records also carry a `social` url       |
| `org_type`          | `type`                           | `"chain"`                               |
| `branch_count`      | `chain.branchCount`              |                                         |
| `publishing_status` | `publishing_status`              | `"publish"`                             |

`tycoon_id` is a separate internal id used only in cabinet URLs
(`/sprav/chain/{tycoon_id}`); it is not the Maps permalink and is not mapped.

### 2. `extract_preload_data(html) -> dict` + `parse_sprav_orgs(preload) -> list[SpravOrg]`

Same module, no I/O, no DB, independently testable. Split in two so the test
fixture can be a small scrubbed JSON rather than a 142 KB HTML page carrying the
operator's uid, phone number, and CSRF token.

Degrades safely: unknown/empty/garbage payload → `[]`, never raises. Missing
per-field values → `None`. A record without both `permanent_id` and
`displayName` is skipped — it cannot be identified downstream.

`SpravListResult` dataclass: `organizations: list[SpravOrg]`,
`needs_manual_action: bool`, `error_code: str | None`, `error_message: str | None`,
`debug_screenshot`/`debug_html` — mirroring the `ScrapeResult` contract so the
failure semantics read the same as every other scraper.

### 3. `scripts/sprav_login.py` — authorization test command

```
python -m scripts.sprav_login [--check]
```

Thin wrapper over `YandexAuthScraper`, **no database** — it tests the login path in
isolation.

- default: `login_manual(path)` — opens a **visible** browser at Passport and waits
  for the operator to sign in by hand, then saves the storage-state.
- `--check`: skip login, run `check_session(path)` against the existing storage-state
  and print the status.
- Exit code `0` only on `SessionStatus.valid`; `2` on `needs_manual_action`; `1`
  otherwise.

### Why manual, not automated (revised 2026-07-15)

The first cut of this design specified headless auto-login with env credentials, with
a headed browser as an escape hatch. Running it against the live Passport disproved
that: `passport.yandex.ru/auth` now redirects to a React passwordless flow
(`/pwl-yandex/auth/add`) whose login field has **no `name` attribute** and a
per-render generated id (`react-aria-«R166b»`). The `input[name="login"]` /
`input[name="passwd"]` selectors cannot match; the observed failure is a 30s
`Page.fill` timeout, with no bot markers on the page — this is a redesign, not a
bot wall.

Any selector hardcoded against that flow goes stale on the next redesign, and 2FA/QR
cannot be automated anyway without violating the no-bypass rule. So `login_manual`
**fills nothing**: it opens Passport, lets the operator authenticate by whatever
method the account uses, and polls for the `Session_id` cookie on a `.yandex.ru`
domain — a completion signal independent of the page's markup. Sessions are
long-lived, so this is a rare, interactive step.

The pre-existing `login(login, password, path)` is left **unchanged and stale**: it
is called by `ScrapeService.login_operator` behind `/api/scraper/yandex/login`, which
runs server-side where a headed browser is impossible. Repairing that API path is out
of scope for this console-only feature; `login()` carries a docstring saying it is
stale and pointing at `login_manual()`.

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
sprav_login  → YandexAuthScraper.login_manual (visible browser, operator signs in)
             → poll for Session_id cookie → .local/yandex-storage-state.json

sprav_orgs   → YandexSpravScraper.list_organizations
                 → Playwright context(storage_state) → /sprav/ -> /sprav/companies
                 → extract_preload_data(html) → parse_sprav_orgs(dict) → list[SpravOrg]
                 → stdout (JSON) + .local/sprav-orgs.json
```

## Error handling

| Condition                            | Outcome                                                |
|--------------------------------------|--------------------------------------------------------|
| storage-state missing/empty          | `needs_manual_action`, `missing_session`, no browser    |
| redirect to passport / captcha wall  | `needs_manual_action`, `access_challenge` + artifacts   |
| preload absent / list empty          | `error_code = "sprav_list_not_found"` + artifacts       |
| unexpected/empty JSON                | parser returns `[]` (no raise)                          |
| network/timeout/other exception      | `error_code = "sprav_scrape_error"`, message attached   |

## Testing

Critical path here is the parser — it is the only pure, deterministic unit.

- `tests/test_sprav_parser.py`:
  - happy path: real captured fixture → expected `SpravOrg` list.
  - empty payload / garbage payload / missing fields → `[]` or `None` fields, no raise.
- No live-network test (constitution: scrapers are not exercised against real sites
  in tests). The Playwright I/O layer is not mocked.

## Discovery outcome (resolved)

The endpoint and payload shape were not assumed by this design: Task 2 opened the
cabinet live with a valid storage-state, established that the list is inlined
rather than fetched, and saved a scrubbed fixture to
`apps/api/tests/fixtures/sprav_companies_preload.json`. The parser is written
against that real payload. See "Confirmed cabinet payload" above.

## Out of scope

- **The reviews feed** — deliberately deferred to its own feature; see below.
- Listing a chain's individual branches (`/sprav/chain/{tycoon_id}`, 209 for the
  big chain).
- Any write action in the cabinet (permanently out under the current
  constitution — see "Replying to reviews" below).
- Persisting cabinet organizations to the `organizations` table / mapping them to
  existing rows.
- A new `ScrapeMode`, an API endpoint, or a web page. Console only for now.
- Captcha bypass.

## Findings banked for the next feature (Task 2, live, 2026-07-15)

Discovery went past this feature's scope and found what the operator actually
wants. Recording it here so the knowledge survives this branch.

### The cabinet does have reviews — on the updates page, not the company pages

`/sprav/chain/{tycoon_id}/updates` renders `initialState.chain.lenta`, an
event feed. Paging is a plain authorized GET:

```
GET https://yandex.ru/sprav/api/chain/{chain_permalink}/{geo_id}/more-events
    ?offset=N&limit=10&total=T&filter=reviews

→ { "lenta":  [ { "type": "reviews",
                  "data": { "company": { "permanent_id": …, "displayName": …, … },
                            "reviews": [ { "id", "rating", "time_created",
                                           "full_text", "snippet", "author",
                                           "comments_count", … } ] } } ],
    "pager":  { "offset": 0, "limit": 10, "total": 58 },
    "filter": "reviews" }
```

Verified live for chain `81562141869` / geo `10000`: `filter=reviews` → 58 review
events across all 209 branches, one time-ordered feed, each carrying a rating, the
full text, the author, and the branch's Maps permalink.

**Why this matters:** it answers the operator's real need — spotting new reviews
without re-scraping every organization — which the organization list in this
feature does not.

Two constraints found the hard way:
- **`limit` is capped at 10 server-side.** A request with `limit=50` comes back
  with `"limit": 10`. 58 reviews = 6 requests; `filter=all` (231 events) = 24.
- `time_created` is epoch **milliseconds**.

### Replying to reviews

Each review carries `cmnt_entity_id`, `cmnt_official_token`, `comments_count`, and
`can_generate_answer`, so the cabinet's reply mechanism is reachable. **It is a
write, and the constitution forbids writes as a hard rule** ("Never publish, edit,
or delete replies on Yandex"; "Out of scope: posting replies"). Building it
requires a constitution amendment first — an explicit decision, not an incidental
one.
