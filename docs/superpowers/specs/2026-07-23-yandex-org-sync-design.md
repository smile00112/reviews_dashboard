# Yandex org sync — design

**Date:** 2026-07-23
**Status:** design, awaiting review

## Goal

Synchronize the list of organization points from the Yandex Business cabinet
(`yandex.ru/sprav/`) into our `organizations` table, packaged as a Claude Code
skill. Read-only against Yandex (constitution hard rule); the only writes are to
our own DB. **Dry-run by default; writes only with `--apply`.**

## Scope

Four chains, each mapped to an existing company (brand) in our DB:

| Cabinet chain | tycoon_id (chain_id) | Our company |
|---|---|---|
| Суши Мастер | 2082553 | Суши Мастер Россия |
| Галерея Суши | *(resolve)* | Галерея Суши Россия |
| Мир Суши | *(resolve)* | Мир Суши Россия |
| Spoke | 57060012 | SPOKE Россия |

tycoon_ids are resolved at runtime from the cabinet company list
(`initialState.companiesList.listCompanies[i].tycoon_id`), matched to our company
by name. Минск (.by) and Подольск (closed, single ordinal) are **out of scope**.

## Non-goals

- No auto-creation of points absent from our DB (report only).
- No deletion (deactivation only).
- No touching `rating` / `review_count` (owned by the review scrapers).
- No changes to review data or scrape flow.

## Components

1. **`app/services/sprav_sync.py`** — pure sync-plan engine.
   - Input: a chain's cabinet branches (`list[SpravBranch]`), the company's
     organizations (`list[Organization]`), and a per-point maps-link resolver
     callback (so the engine stays I/O-free and testable).
   - Output: `SyncPlan` with four buckets:
     - `deactivate: list[Organization]` — our active points confirmed gone.
     - `update: list[FieldUpdate]` — matched points with field diffs.
     - `new_in_cabinet: list[SpravBranch]` — cabinet branches we couldn't match.
     - `ambiguous: list[Organization]` — our points that neither matched nor can
       be safely deactivated (no `external_id`).
   - Deterministic, no network, no DB. Contract-tested.

2. **`scripts/sprav_sync.py`** — CLI orchestrator.
   - For each (tycoon_id → company) pair: read branches via Playwright + saved
     cookies (browserless `requests` currently redirect-loops), match with
     `services/sprav_branch_match.match_branches`, build the plan, print a
     report. With `--apply`, commit the writes.
   - `--company "<name>"` limits to one brand; default runs all four.
   - `--apply` performs writes (default off).
   - `--delay <seconds>` (default 2.0) — pause between per-point `/p/edit/main`
     fetches, and between branch-list pages, to rate-limit (matches the other
     scrapers' `time.sleep`).
   - Exit codes mirror the other scripts: 0 ok, 2 needs_manual_action
     (expired session / captcha), 1 error.

3. **Skill `.claude/skills/sync-yandex-orgs/SKILL.md`** — modeled on
   `collect-reviews`: when to use, how to run (dry-run first, then `--apply`),
   how to read the report, session-refresh pointer (`scripts.sprav_login`).

4. **`tests/test_sprav_sync.py`** — contract tests for the plan engine,
   especially the deactivation-safety rule and the two-way `external_id` branch
   of the normalized_url rule.

## Matching

Reuse `services/sprav_branch_match`:
1. `external_id == permanent_id` (exact, confidence 1.0).
2. Conservative address fallback (city + house + street-token overlap), which is
   **calibrated** against the exactly-matched branches first and abandoned if it
   produces even one wrong answer. An org is claimed at most once.

## Sync rules

### Deactivation (safety-critical)
Set `is_active = false` **only** for an org that:
- belongs to the chain's company, **and**
- has a non-null `external_id`, **and**
- its `external_id` is **not** in the chain's set of cabinet `permanent_id`s, **and**
- is currently `is_active = true`.

Orgs with a **null** `external_id` that did not match go to `ambiguous` (report
only) — never deactivated. Rationale: 272 of 596 orgs lack `external_id`; a
missing match there means "we can't identify it", not "removed upstream". Only an
`external_id`-confirmed absence is a real removal signal.

### New in cabinet
A cabinet branch that matched no org → `new_in_cabinet` (report only). No create.

### Field updates on matched points
- `name` ← cabinet `name` (when different).
- `address` ← cabinet `address` (when different; cabinet form is longer, carries
  federal district / region).
- `region` ← cabinet `region` **only when ours is null/empty**.
- `is_active` ← `false` when cabinet `publishing_status == "closed"`. `publish`
  does **not** auto-reactivate (never flip false→true automatically).
- `normalized_url` / `external_id` — see below.

### normalized_url + external_id (the maps link)
Split by whether our org already has an `external_id`:

- **Org WITH `external_id`:** the cabinet `permanent_id` is already known from the
  branch list (it equals the `/p/edit/main` maps-link id — verified). Do **not**
  load edit/main. Update `normalized_url` **only if** the `permanent_id` embedded
  in our current `normalized_url` differs from the branch `permanent_id` (a point
  whose Maps card was recreated under a new id) → set to
  `https://yandex.ru/maps/org/<permanent_id>`. Same id → leave ours (keeps slug).

- **Org WITHOUT `external_id`** (address-matched; its `normalized_url` is a short
  `/maps/-/CODE` link with no permanent_id): load the branch's
  `/sprav/<permanent_id>/p/edit/main`, read
  `initialState.edit.relatedProfiles.maps.external_path`, and set
  `external_id = permanent_id` and `normalized_url = https://yandex.ru/maps/org/<permanent_id>`.
  This is the only case that loads edit/main, bounding the expensive per-point
  Playwright request to the address-matched subset. `--delay` applies between
  these fetches.

## Data flow

```
resolve tycoon_ids (cabinet company list, Playwright)
  for each (tycoon_id, company):
    branches   = SpravChainReader/Playwright list_branches(tycoon_id)   # paged, delay between pages
    orgs       = company's organizations (DB)
    calibration= calibrate(branches, orgs); abort if untrustworthy
    matches    = match_branches(branches, orgs)
    plan       = SpravSync.plan(branches, orgs, matches, edit_main_resolver)  # resolver loads edit/main only for no-external_id matched orgs, with delay
    print report(plan)
    if --apply: apply(plan)   # DB writes in one transaction per chain
```

## Error handling

- Missing/expired session or captcha → `needs_manual_action`, exit 2, message
  points to `python -m scripts.sprav_login`. No bypass.
- Address fallback produced any wrong calibration answer → refuse to use it,
  report, exit 1 (same contract as `sprav_chain_ratings`).
- Cabinet throttling on edit/main → skip that point's maps-link update (leave its
  url/external_id untouched), count it in the report; never abort the whole run
  for one point.
- `--apply` writes per chain inside a transaction; a failure rolls back that
  chain only.

## Testing

`tests/test_sprav_sync.py` (SQLite, like the rest of the suite):
- deactivation fires only for external_id-confirmed absence; null-external_id
  unmatched orgs land in `ambiguous`, never deactivated.
- matched-with-external_id: normalized_url updated only on id change; slug kept
  when id matches.
- matched-without-external_id: external_id + normalized_url filled from the
  resolver; resolver called only for this subset.
- field updates: region only when empty; closed→is_active false; publish never
  reactivates; rating/review_count never written.
- new_in_cabinet collects unmatched branches.

## Open questions

None — all rules confirmed with the operator.
```
