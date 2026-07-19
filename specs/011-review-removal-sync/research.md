# Phase 0 Research: Review Removal Sync

No NEEDS CLARIFICATION markers remained in the spec; research resolves design unknowns against the existing codebase.

## R1. How to determine "full pass" per scraper

**Decision**: Track the pagination-loop termination cause inside each paginating scraper and expose it as `ScrapeResult.full_pass: bool = False` (default false = safe).

- `yandex_http.YandexHttpScraper.scrape` (`apps/api/app/scraper/yandex_http.py`): `full_pass = True` only when the loop ended via the "no fresh reviews on page > 1" exhaustion branch (line ~106) **and** no page was skipped by the transient-fetch-error `continue` (line ~79) **and** neither `limit` nor `max_pages` cap stopped collection mid-list. A skipped page is a hole in coverage → partial. `metrics_only` → always `False` (no review coverage claimed).
- `twogis_api.TwogisApiScraper._fetch_reviews`: `full_pass = True` only when the offset loop ended because the API returned an empty/short page (natural end of list), not because `len(collected) >= limit` or `pages >= max_pages`.
- Playwright scroll modes (`yandex_public`, `yandex_auth`, `yandex_scrapeops`): never set the flag (stays `False`). They cannot prove list coverage; the automated reviews job never uses them anyway (`PLATFORM_SCRAPE_MODE` pins `public_http`/`twogis_api`).

**Rationale**: The loop already distinguishes these exits; recording the cause is the only reliable, provider-local way to prove coverage. Defaulting to `False` satisfies the spec's safe-default assumption ("coverage undeterminable ⇒ partial").

**Amendment (implementation)**: exhaustion alone proved insufficient — Yandex serves at most ~600 reviews over `?page=N` (page 13 returns HTTP 200 with no review blocks, README), so a big org "exhausts" while most of its list was never seen. The scraper-level flag is therefore **corroborated** in `ScrapeService._persist_scrape_result`: `run.full_pass = result.full_pass AND counter is not None AND len(reviews) >= counter` (counter = the org's stored platform review count). Removal marking keys off the corroborated `run.full_pass`. Orgs above the ceiling never achieve a corroborated full pass: they re-scrape on mismatch but never mark removals — safe, and no worse than the pre-feature behavior.

**Alternatives considered**: (a) Trusting exhaustion alone — rejected (mass false removals for >600-review orgs). (b) A separate "coverage" enum (full/partial/unknown) — rejected as YAGNI; bool + default false encodes unknown=partial.

## R2. Removal marking mechanism

**Decision**: After a successful upsert of a `full_pass` result, mark as removed every review of that **organization + platform** whose `content_hash` is not in the set of hashes just seen: `UPDATE reviews SET removed_at = now WHERE organization_id = :org AND platform = :platform AND removed_at IS NULL AND content_hash NOT IN (:seen_hashes)`. Implemented as `ReviewService.mark_removed_missing(organization_id, platform, seen_hashes, now)`, called from `ScrapeService._persist_scrape_result` only on the success path with `result.full_pass`.

**Rationale**: The seen-hash set is exact and immune to clock ordering (the alternative `last_seen_at < run_start` cutoff races with the upsert's own `now` and with concurrent runs). Scale is small (≤ ~2k hashes per org). Scoping by platform uses the same `platform` value the upsert derives from `scrape_mode`, so a Yandex pass can never touch 2GIS rows (FR-011).

**Alternatives considered**: `last_seen_at` timestamp cutoff — simpler SQL but ordering-fragile; deleting rows — forbidden by FR-001/retention.

## R3. Reappearance un-marking

**Decision**: `ReviewService._apply_update` (both the normal update path and the IntegrityError collision path funnel through it) sets `existing.removed_at = None` unconditionally alongside `last_seen_at = now`.

**Rationale**: Identity comes from `content_hash`, so a reinstated review resolves to its existing row by construction — no duplicate possible without breaking the frozen dedup contract. Un-marking on *any* sighting (even during a partial pass) is correct: being seen proves presence.

## R4. Zero-result full pass guard (FR-008)

**Decision**: If a full pass yields 0 reviews while the organization has ≥ 1 non-removed collected review for that platform, skip removal marking and finalize the run as `failed` with `error_code="empty_full_pass"` — **unless** the organization's stored platform counter (`Organization.<platform>_review_count`) is exactly `0`, which corroborates a genuine wipe-out and allows marking.

**Rationale**: An empty page-1 that parses "successfully" is indistinguishable from a parser/markup regression; failing loudly reuses the existing failure surface (run status, error code, attention rules) instead of a new notification channel. The counter==0 escape hatch keeps the legitimate "all reviews removed" case reconcilable.

**Alternatives considered**: Always allow (dangerous mass-flag on parser regression); always block (org with a real wipe-out re-scraped every cycle forever).

## R5. Job trigger rule and full-coverage overrides

**Decision**: In `JobRunner._run_reviews`:
- `scraped_before` counts only `removed_at IS NULL` rows.
- Trigger on `platform_total != scraped_before` (both directions); `platform_total is None` keeps the existing skip-with-reason; equality skips unless R6 forces a pass.
- The scrape call becomes `execute_run(scrape_run.id, limit=math.inf, max_pages=ALL_REVIEWS_MAX_PAGES)` — the same uncapped-pagination pattern `scripts/scrape_reviews.py --all-reviews` already uses; the constant moves to a shared importable location (e.g. `app/core/config.py` or `scraper` module) so script and runner share one value.

**Rationale**: Without uncapped pagination the settings caps (`http_scrape_limit=150`, `max_pages=5`) make `full_pass` unreachable for any org above the cap, so removal detection would silently never engage — the override is what makes FR-002 attainable. `max_pages` stays as runaway protection; hitting it ⇒ partial pass ⇒ no removals (safe).

**Alternatives considered**: Raising global settings defaults — rejected: manual/API-triggered scrapes keep their cheap caps; only the automated job needs full coverage.

## R6. Periodic forced full pass (FR-010)

**Decision**: Optional `force_full_every_days: int` key in the existing `Job.options` JSON (validated ≥ 1 when present, like `delay_seconds`). When counters match, the runner checks the latest `scrape_runs` row for that org with `status=success AND full_pass=true` and the platform's job mode; if none or older than the interval → scrape anyway with reason "forced full refresh (last full pass ...)".

**Rationale**: `scrape_runs` already stores per-org run history and gains `full_pass` in this feature — no new table or column on Organization. Absent/disabled key ⇒ behavior identical to R5 (FR-010 default).

**Alternatives considered**: `Organization.last_full_scrape_at` denormalized column — rejected: derivable from `scrape_runs` at tens-of-orgs scale; avoids a second write path.

## R7. Persistence & API surface for removal state

**Decision**:
- `reviews.removed_at` nullable `timestamptz`; NULL = present on platform. No backfill needed (existing rows start present, FR-012).
- `scrape_runs.full_pass` boolean `NOT NULL DEFAULT false` (FR-003; historical runs correctly read as partial).
- Migration `0016_review_removal_tracking.py`, additive only.
- Review API responses gain `removed_at`; list endpoints gain `removed` query param: `active` (default — excludes removed), `removed` (only removed), `all`. Applies to per-org listing and the global feed; summary/analytics endpoints are untouched this feature (spec assumption).
- `ScrapeRun` schema exposes `full_pass`.
- Web: `removed_at`/`full_pass` in `lib/types.ts`; org reviews table gets a "show removed" toggle mapping to the `removed` param and a labeled badge with the removal date.

## R8. Twice-daily schedule (FR-009)

**Decision**: Documentation + configuration only. Recommended values (Europe/Moscow): metrics jobs `0 4,16 * * *`, reviews jobs `0 5,17 * * *` — reviews trail metrics by 1h in both cycles so the comparison sees fresh counters. Applied via existing `PATCH /api/jobs/{id}` (`schedule_cron` validated by `validate_cron`) or the `/jobs` page; overlap protection (`JobAlreadyRunning`, 409) already exists. Documented in quickstart + README ops note.

**Rationale**: The scheduler re-reads per-job cron from the DB; multi-slot cron expressions are already supported by `CronTrigger.from_crontab`. No code path changes.
