---
name: sync-yandex-orgs
description: Use when synchronizing the organization/point list from the Yandex Business cabinet (yandex.ru/sprav) into our organizations table — reconciles branches per chain, reports new/removed points, updates matched fields. Triggers on "синхронизируй точки", "синхронизация организаций из яндекс бизнеса", "sync org list", "sprav sync", "сверь точки с кабинетом".
---

# Syncing the Yandex cabinet point list

Read-only against Yandex — the cabinet is only read. The only writes are to our
own DB, and they are **opt-in**: the script prints a dry-run report by default
and commits only with `--apply`. Always run the dry-run first and show the report
before applying.

Run from `apps/api`:

```bash
cd apps/api
python -m scripts.sprav_sync                          # dry-run, all 4 chains
python -m scripts.sprav_sync --company "SPOKE Россия"  # one brand
python -m scripts.sprav_sync --apply                  # write the changes
python -m scripts.sprav_sync --company "Суши Мастер Россия" --apply --delay 3
```

## Flags

| Flag | Meaning |
|---|---|
| *(none)* | Dry-run over every chain that maps to a company. Prints the report, writes nothing. |
| `--company "<exact name>"` | Limit to one company (our DB name, e.g. `"Мир Суши Россия"`). |
| `--apply` | Commit the plan (deactivations + field updates). Default is dry-run. |
| `--delay <seconds>` | Pause between per-point `/p/edit/main` loads, short-link resolutions, and branch-list pages (default `2`). Raise it if throttled. |
| `--resolve-links` | Also match points that have **no `external_id`** by resolving their `/maps/-/CODE` short link to a real `permanent_id` and pairing it with the cabinet branch of that id (exact, not fuzzy). One public-Maps request per such point. Backfills `external_id` + `normalized_url` on a match. |
| `--resolve-proxy` | Route `--resolve-links` requests through `PROXY_POOL`. Off by default — the single residential proxy hangs ~30 s/request; a direct request is far faster. |

## Prerequisite: a valid cabinet session

Needs the saved operator cookies (`.local/yandex-storage-state.json`). If the run
prints `Session invalid or captcha` and exits with code **2**, refresh the
session (opens a visible browser for the operator to sign in, incl. 2FA):

```bash
python -m scripts.sprav_login
```

## What it does per chain

1. Resolves the chain's short `tycoon_id` from the cabinet company list (the
   branch-list URL needs `tycoon_id`, **not** `permanent_id`) and maps it to our
   company by name.
2. Reads the full branch list via Playwright + cookies (browserless `requests`
   currently redirect-loop against the cabinet).
3. Matches branches to the company's organizations, in order:
   1. `external_id == permanent_id` (exact).
   2. conservative address fallback — **calibrated** against the exact matches and
      **dropped to permalink-only** if it produces even one wrong answer.
   3. *(with `--resolve-links`)* short-link resolution: follow a no-`external_id`
      point's `/maps/-/CODE` link to its real `permanent_id` and pair it with the
      cabinet branch of that id. Exact. This is how the `/maps/-/CODE`-imported
      points (which the address fallback can't read) get synced and get their
      `external_id`/`normalized_url` backfilled. Points carrying only a 2GIS link
      have no Yandex identity to resolve and stay `ambiguous`.
4. Builds and prints a plan in the buckets below.

## The four report buckets

- **deactivate** — our *active* point whose `external_id` is set but is **absent**
  from the cabinet's permalinks → `is_active = false`. This is the only removal
  signal we trust.
- **update** — a matched point whose fields differ (see below).
- **new in cabinet** — a cabinet branch that matched no point. **Report only** —
  never auto-created.
- **ambiguous** — our point with **no** `external_id` that matched nothing. Left
  **untouched** (a missing match there means "unidentified", not "removed" — most
  of these are unmatched only because they lack an `external_id`).

## Field updates on matched points

Written only under `--apply`:

- `name`, `address` — from the cabinet when different.
- `region` — filled **only when ours is empty** (never overwritten).
- `is_active` — set `false` when cabinet `publishing_status == "closed"`.
  `publish` never auto-reactivates.
- `normalized_url` / `external_id`:
  - point **with** `external_id` → `normalized_url` rewritten only if the
    permanent_id it embeds changed (Maps card recreated); slug kept otherwise. No
    edit/main fetch.
  - point **without** `external_id` (short `/maps/-/CODE` url) → the branch's
    `/p/edit/main` Maps link is loaded and both `external_id` and `normalized_url`
    are filled. This is the only path that loads edit/main, so it is the only
    slow part — bounded to the address-matched subset and paced by `--delay`.

**`rating` and `review_count` are never written** — the review scrapers own them
(see the `collect-reviews` skill).

## Scope

Four chains → four brands: Суши Мастер, Галерея Суши, Мир Суши, Spoke.

- The branch list is read with **`status=all`**. Its default is `status=opened`,
  which hides closed branches — for «Суши Мастер» that is 209 of 357 (147 closed,
  1 temporarily_closed). `all` returns the full set the cabinet header counts, and
  each branch's `publishing_status` then drives the is_active rule. Only
  `closed` deactivates; `temporarily_closed` is left active (may reopen).
- A brand can appear as **several same-named chains** (e.g. a 3-branch `.by`
  «Суши Мастер» beside the real 209-branch one). Chains are processed
  largest-first and each brand is synced by its **biggest chain only**; the rest
  are skipped with a `skip: … already synced by a larger chain` note. This guard
  exists because a small namesake would otherwise see every other branch as
  absent and wrongly deactivate it.
- Cabinet entries with no matching company are skipped with a `skip:` note.

## Exit codes

`0` ok · `2` needs_manual_action (expired session / captcha — run `sprav_login`)
· `1` error (e.g. address fallback untrustworthy).

## Verify after changing the sync

```bash
cd apps/api && pytest tests/test_sprav_sync.py -q
```

The plan engine lives in `app/services/sprav_sync.py`; matching in
`app/services/sprav_branch_match.py`. `test_sprav_sync.py` is the contract —
treat "deactivation only on external_id-confirmed absence" and "rating/
review_count never written" as invariants.
