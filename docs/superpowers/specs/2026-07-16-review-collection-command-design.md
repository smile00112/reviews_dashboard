# Review-collection console command + skill — design

**Date:** 2026-07-16
**Status:** approved (brainstorming), pending implementation plan

## Goal

One operator command to collect **reviews** (not just metrics) for organizations
already in the database, with:

- a single org (`--org-id`) or every org (`--all`);
- either the settings-configured cap or **all** available reviews (`--all-reviews`);
- a platform selector (`--platform yandex|2gis`);
- organization headline info (name, rating, review count, rating count, address)
  refreshed as part of the same run.

Plus a Claude skill so the command is invoked consistently without re-deriving flags.

## Context

### Why this is needed

`POST /api/organizations/{id}/scrape` collects reviews but is per-org, HTTP-only, and
capped by `http_scrape_limit` (150) / `http_scrape_max_pages` (5) with no override. A
2026-07-16 run against org `007cab4a…` (1110 reviews on Yandex) inserted exactly 150 —
the cap, not the org's real volume. There is no console route to a full collection.

`scripts/scrape_metrics.py` is deliberately **metrics-only** and writes no `ScrapeRun`;
it is not the place for review collection (mixing the two blurs both).

### What already works (and must be reused, not duplicated)

`ScrapeService._persist_scrape_result` already does everything the persistence side of
this feature needs, and is **already platform-correct**:

- `ReviewService.upsert_reviews` derives `source` / `platform` from the scrape mode
  (`twogis_api` → `2gis`/`gis2`, else `yandex_maps`/`yandex`) and applies the
  `content_hash` dedup contract.
- `OrganizationService.update_scrape_status(org_id, platform, …)` writes **only that
  platform's** columns (`_PLATFORM_STATUS_COLUMNS[platform]`) — this is the org-info
  refresh the goal asks for, already wired into every successful scrape.
- `DashboardService.capture_snapshot` records the daily rating snapshot.
- The run's `ScrapeRun` row carries status/timestamps/counts and debug artifacts.

### Correcting the record: the 2026-07-10 objection is stale

`docs/superpowers/specs/2026-07-10-bulk-metrics-scraper-design.md` justified a
standalone CLI by arguing that routing 2GIS through `ScrapeService` would
"(a) feed the wrong URL and (b) clobber the Yandex rating", and that fixing it
"means reworking the tested review-persistence path".

Half of that is no longer true. `update_scrape_status` now takes a `platform`
argument and writes only that platform's columns, so **(b) cannot happen**. Only
**(a)** remains: `ScrapeService._scrape_organization` is handed `org.yandex_url`
unconditionally (`scrape_service.py:86` and `:99`), regardless of mode.

That is a URL-selection bug in the *caller*, not a defect in the persistence path.
Fixing it is a small, testable change — not the rework the older doc feared. This
design therefore fixes the root cause instead of routing around it.

## Approach

Thin CLI over `ScrapeService`. Rejected alternatives:

- **Standalone script** (the `scrape_metrics.py` shape): would duplicate
  `_persist_scrape_result` — dedup + org refresh + snapshot + run finalization,
  ~80 lines. That duplication is exactly how the `yandex_url` bug survived. Rejected.
- **`--reviews` flag on `scrape_metrics.py`**: that script is metrics-only by design
  and writes no `ScrapeRun`. Rejected.

## Changes

### 1. Fix platform URL selection (`app/services/scrape_service.py`)

Add a helper mapping mode → URL attribute, mirroring the existing `_mode_platform`:

```python
def _mode_url(org, mode: ScrapeMode) -> str | None:
    return org.gis2_url if mode == ScrapeMode.twogis_api else org.yandex_url
```

Use it at both call sites (single-org path and the `/scrape/all` child loop) in place
of `org.yandex_url`. An org with no URL for the requested platform finalizes as
`failed` / `no_url` rather than scraping the wrong platform's link.

This also fixes `POST /api/organizations/{id}/scrape` with `mode=twogis_api`, which
today silently scrapes the Yandex URL.

### 2. Per-run limit override (scrapers + service)

`YandexHttpScraper.scrape` and `TwogisApiScraper.scrape` read `settings.http_scrape_limit`
/ `http_scrape_max_pages` (resp. `twogis_review_limit`) internally. Add optional
`limit` / `max_pages` parameters that default to `None` → fall back to the settings
value, preserving today's behaviour for every existing caller.

`ScrapeService.execute_run` gains an optional `limit`/`max_pages` override passed
through to the scraper. The API path passes nothing and is unchanged.

Three distinct states, so `None` must not be overloaded:

| Caller intent | `limit` | `max_pages` |
|---|---|---|
| default (API, existing callers) | `None` → `settings.http_scrape_limit` (150) | `None` → settings (5) |
| explicit cap | `int` | `int` |
| `--all-reviews` | `math.inf` | `ALL_REVIEWS_MAX_PAGES` = 100 |

`math.inf` is a valid `>=` comparand against `len(collected)` in the existing loop
guard, so "unbounded" needs no branching — only the page ceiling changes. Pagination
is already self-terminating ("no new reviews on a non-first page → stop"), so the
ceiling is a runaway guard, not the expected stop condition. At ~50 reviews/page it
covers ~5000 reviews — comfortably above the largest known org (1110).

### 3. New CLI: `apps/api/scripts/scrape_reviews.py`

Mirrors `scripts/scrape_metrics.py` (argparse, `SessionLocal`, `RunLogger`, `--dry-run`).

```
python -m scripts.scrape_reviews --org-id <uuid>
python -m scripts.scrape_reviews --all
    [--platform {yandex,2gis}]     default: yandex
    [--mode {public,public_http,operator_auth,scrapeops,twogis_api}]
    [--all-reviews]
    [--limit N] [--offset N]
    [--dry-run] [--log-file PATH]
```

- `--org-id` / `--all` — mutually exclusive, exactly one required.
- `--platform` — selects both the URL column and the default mode:
  - `yandex` → `public_http` (the only Yandex mode that can use the proxy pool;
    `public` drives Chromium, which cannot authenticate against the SOCKS5 pool)
  - `2gis` → `twogis_api`
- `--mode` — overrides the default. A mode belonging to another platform
  (e.g. `--platform 2gis --mode public_http`) is rejected at startup.
- `--all-reviews` — lift the settings cap (see §2). Omitted = settings values (150/5).
- `--limit` / `--offset` — how many **organizations** to process (not reviews); for
  test batches. Named to match `scrape_metrics.py`.
- `--dry-run` — print the plan (org, mode, URL); scrape nothing, write nothing.

  **Corrected during implementation.** This originally specified `scrape_metrics.py`'s
  shape — scrape, then `rollback()`. That is impossible here: `ScrapeService` commits
  its own writes, so a rollback afterwards has nothing to undo. The first
  implementation shipped exactly that bug — a `--dry-run` wrote 150 reviews. Preview
  semantics is the honest option when the persistence path owns its transactions.

Each org gets its own `ScrapeRun` via `ScrapeService.create_run` + `execute_run`
(constitution: every attempt produces a `ScrapeRun`). `--all` creates one run per org
rather than a parent bulk run: the CLI already reports aggregate progress, and per-org
rows keep failures individually attributable.

### 4. Skill: `.claude/skills/collect-reviews/SKILL.md`

Documents when to reach for the command and how to pick flags: platform → mode
mapping, when `--all-reviews` is warranted, that `public` mode cannot use the proxy
pool, and to check `needs_manual_action` runs for 429/captcha rather than reading a
zero-review success as "no reviews".

### 5. README

Add `scrape_reviews` to the **Operator Scripts** section, alongside `scrape_metrics`,
noting the platform/mode relationship and the cap behaviour.

## Error handling

Unchanged from `ScrapeService`, which already satisfies the constitution's
debuggability rule: every attempt writes a `ScrapeRun` with status/timestamps/counts;
challenges (429, captcha, bot wall) surface as `needs_manual_action` with debug
artifacts; failures record `error_code`/`error_message`. The CLI adds only reporting:
per-org progress lines and a final `success/failed/manual_action/skipped` summary.

Orgs missing the platform URL are skipped with an explicit `skip (no url)` line —
they must not silently count as successes.

## Testing

Critical-path tests (constitution requires dedup / hash / API contract / persistence
coverage; full per-file TDD is not required):

1. `_mode_url` returns `gis2_url` for `twogis_api`, `yandex_url` otherwise.
2. `ScrapeService` with `mode=twogis_api` scrapes the org's `gis2_url` (regression
   test for the bug in §1) — fake scraper asserting the URL it received.
3. An org with no URL for the requested platform → `failed`/`no_url`, no scraper call.
4. Scraper `limit`/`max_pages` override: explicit value wins; `None` falls back to
   settings (guards the existing callers' behaviour).
5. CLI arg validation: `--org-id` + `--all` together rejected; neither rejected;
   cross-platform `--mode` rejected.

Existing suite (296 tests) must stay green — the override defaults exist precisely so
current callers are unaffected.

## Out of scope

- Changing any org's stored `preferred_scrape_mode` (a separate data decision).
- Backfilling `yandex_url` for orgs that have none (e.g. `95debcf5…` Ачинск-01).
- Fixing `GET /api/organizations` 500 on null-`yandex_url` rows (pre-existing, unrelated).
- Google as a platform: no scraper exists.
