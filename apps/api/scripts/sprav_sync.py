"""Synchronize the Yandex Business cabinet's point list into ``organizations``.

Read-only against Yandex (constitution hard rule): the cabinet is only read. The
only writes are to our own DB, and they are **opt-in** — the script prints a
dry-run report by default and applies changes only with ``--apply``.

    python -m scripts.sprav_sync                     # dry-run, all 4 chains
    python -m scripts.sprav_sync --company "Суши Мастер Россия"
    python -m scripts.sprav_sync --apply             # write the changes
    python -m scripts.sprav_sync --company "SPOKE Россия" --apply --delay 3

Per chain it: reads the cabinet branch list, matches branches to our company's
organizations (``services.sprav_branch_match``), builds a :class:`SyncPlan`
(``services.sprav_sync``), prints the report, and — with ``--apply`` — commits.

Rules (see ``docs/superpowers/specs/2026-07-23-yandex-org-sync-design.md``):
deactivate only external_id-confirmed removals; report (never create) unmatched
cabinet branches; update name/address/region(if empty)/is_active(closed)/
normalized_url. rating/review_count are never touched.

The cabinet's short ``tycoon_id`` (the branch-list key) is resolved at runtime
from the cabinet company list and mapped to our companies by name.

Exit codes: 0 ok, 2 needs_manual_action (expired session / captcha), 1 error.
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from dataclasses import dataclass

import requests
from playwright.sync_api import sync_playwright

from app.core.config import settings
from app.scraper.markers import BOT_MARKERS
from app.scraper.yandex_public import YandexPublicScraper
from app.scraper.yandex_sprav import _ORG_ARRAY_PATH, extract_preload_data
from app.scraper.yandex_sprav_chain import (
    parse_branch_total,
    parse_chain_branches,
    parse_chain_name,
)
from app.services.sprav_branch_match import calibrate, match_branches, normalize
from app.services.sprav_sync import SyncPlan, apply_plan, build_plan, maps_url_for

# A Maps org url embeds the permanent_id, with or without a slug.
_MAPS_PID_RE = re.compile(r"/maps/org/(?:[^/]+/)?(\d+)")
# Stop resolving after this many consecutive unresolved links — a run of them is
# the public Maps host rate-limiting this IP (429), and further requests only
# provoke it. The already-resolved matches are kept.
_RESOLVE_ABORT_STREAK = 8


def resolve_short_link(http: requests.Session, url: str | None, pool=None) -> str | None:
    """Follow a `/maps/-/CODE` short link to its `/maps/org/<permanent_id>`,
    returning the permanent_id, or None when it can't be resolved.

    Public Maps, no cabinet cookies — a plain redirect resolution. Routed through
    the rotating proxy pool when configured (a datacenter IP gets 429'd by Maps
    fast — measured), retrying on the next proxy on a block. Kept out of the pure
    engine because it is network I/O.
    """
    if not url:
        return None
    use_pool = pool is not None and pool.enabled
    tries = (min(settings.proxy_pool_max_tries, len(pool)) or 1) if use_pool else 1
    for _ in range(tries):
        proxies = pool.next_requests_proxies() if use_pool else None
        try:
            response = http.get(url, allow_redirects=True, timeout=30, proxies=proxies)
        except requests.RequestException:
            continue
        if response.status_code != 200:
            continue  # 429/5xx — try the next proxy
        match = _MAPS_PID_RE.search(response.url or "")
        return match.group(1) if match else None
    return None

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_MANUAL = 2

MAX_BRANCH_PAGES = 100
# Retry an empty branch page this many times before concluding the list ended —
# an empty page short of the reported total is a throttle stub, not the end.
_BRANCH_PAGE_RETRIES = 4
_BRANCH_RETRY_BACKOFF = 3.0


class ManualActionNeeded(Exception):
    """A cabinet page demanded a human (expired session / captcha / passport)."""


@dataclass
class CabinetChain:
    tycoon_id: str
    permanent_id: str
    name: str
    branch_count: int = 0


class Cabinet:
    """One Playwright browser + operator cookies, reused for every cabinet read.

    Browserless ``requests`` to the cabinet currently redirect-loop, so every
    page (company list, branch pages, per-point edit/main) is read through
    Playwright with the saved storage state.
    """

    def __init__(self, storage_state_path: str, timeout_ms: int) -> None:
        self._pub = YandexPublicScraper()
        self._timeout = timeout_ms
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=True)
        self._ctx = self._browser.new_context(
            storage_state=storage_state_path,
            locale=self._pub.LOCALE,
            extra_http_headers=self._pub.EXTRA_HTTP_HEADERS,
        )
        self._page = self._ctx.new_page()

    def close(self) -> None:
        self._browser.close()
        self._pw.stop()

    def preload(self, url: str) -> dict:
        """Load a cabinet URL and return its inlined state, or raise on a challenge."""
        self._page.goto(url, wait_until="networkidle", timeout=self._timeout)
        html = self._page.content()
        if "passport.yandex" in self._page.url or any(
            marker.lower() in html.lower() for marker in BOT_MARKERS
        ):
            raise ManualActionNeeded(
                "Session invalid or captcha — run: python -m scripts.sprav_login"
            )
        return extract_preload_data(html)

    def chains(self) -> list[CabinetChain]:
        """The cabinet's chains, with the short tycoon_id the branch list needs."""
        preload = self.preload(settings.sprav_companies_url)
        raw = preload
        for key in _ORG_ARRAY_PATH:
            raw = raw.get(key) if isinstance(raw, dict) else None
        result: list[CabinetChain] = []
        for item in raw or []:
            if not isinstance(item, dict):
                continue
            tycoon = item.get("tycoon_id")
            pid = item.get("permanent_id")
            name = item.get("displayName")
            chain = item.get("chain") if isinstance(item.get("chain"), dict) else {}
            count = chain.get("branchCount")
            if tycoon and pid and name and item.get("type") == "chain":
                result.append(
                    CabinetChain(str(tycoon), str(pid), str(name),
                                 int(count) if isinstance(count, int) else 0)
                )
        return result

    def branches(self, tycoon_id: str, delay: float):
        """Every branch of a chain, paging the cabinet list (delay between pages).

        ``status=all`` is essential: the branch list defaults to
        ``status=opened``, which hides closed/temporarily-closed branches — for
        «Суши Мастер» that is 209 of 357. ``all`` returns the full set the
        cabinet header counts, and each branch's ``publishing_status`` then drives
        the is_active rule (a matched closed branch → is_active=false).
        """
        seen: set[str] = set()
        collected = []
        name = total = None
        for page in range(1, MAX_BRANCH_PAGES + 1):
            fresh: list = []
            # A page that yields nothing while the reported total isn't covered is
            # the cabinet's throttle stub, not the end — retry it with backoff
            # before giving up, so a transient throttle can't truncate the list
            # (a truncated list would look like mass removals).
            for attempt in range(_BRANCH_PAGE_RETRIES):
                preload = self.preload(
                    f"https://yandex.ru/sprav/chain/{tycoon_id}/branches?page={page}&status=all"
                )
                name = name or parse_chain_name(preload)
                total = parse_branch_total(preload) or total
                fresh = [b for b in parse_chain_branches(preload) if b.permanent_id not in seen]
                if fresh or (total is not None and len(collected) >= total):
                    break
                time.sleep(delay + _BRANCH_RETRY_BACKOFF * (attempt + 1))
            if not fresh:
                break  # genuine end, or throttled past retries (complete=False below)
            seen.update(b.permanent_id for b in fresh)
            collected.extend(fresh)
            if total is not None and len(collected) >= total:
                break
            time.sleep(delay)
        complete = total is not None and len(collected) >= total
        return collected, name, total, complete

    def maps_url(self, permanent_id: str) -> str | None:
        """The point's Maps link from its /p/edit/main page, or None on trouble."""
        try:
            preload = self.preload(f"https://yandex.ru/sprav/{permanent_id}/p/edit/main")
        except ManualActionNeeded:
            return None  # transient — the caller leaves the point untouched
        maps = (
            preload.get("initialState", {})
            .get("edit", {})
            .get("relatedProfiles", {})
            .get("maps")
        )
        path = maps.get("external_path") if isinstance(maps, dict) else None
        return f"https://yandex.ru{path}" if path else None


def _load_companies():
    """All companies with their branch organizations, detach-safe."""
    from app.core.database import SessionLocal
    from app.models.company import Company

    session = SessionLocal()
    companies = session.query(Company).all()
    for company in companies:
        _ = company.name, company.id
        for org in company.branches:
            _ = org.id, org.name, org.city, org.external_id, org.region, \
                org.address, org.normalized_url, org.is_active
    return session, companies


def _match_chain_to_company(chain: CabinetChain, companies):
    """The company whose name contains the cabinet chain's name tokens."""
    chain_tokens = set(normalize(chain.name).split())
    if not chain_tokens:
        return None
    for company in companies:
        if chain_tokens <= set(normalize(company.name).split()):
            return company
    return None


def _resolve_link_matches(matches, orgs, delay: float, use_proxy: bool = False) -> set:
    """Pair still-unmatched, no-external_id points to cabinet branches by
    resolving their `/maps/-/CODE` link to a permanent_id.

    Mutates ``matches`` in place (an unmatched branch's entry gets the org and
    ``method="short_link"``) and returns the set of branch permanent_ids matched
    this way, so the caller's resolver can skip the edit/main fetch for them.
    """
    branch_by_pid = {m.branch.permanent_id: m for m in matches}
    matched_pids = {m.branch.permanent_id for m in matches if m.organization}
    matched_org_ids = {m.organization.id for m in matches if m.organization}
    candidates = [o for o in orgs if not o.external_id and o.id not in matched_org_ids]
    # Only a Yandex short/maps link can be resolved. Points carrying only a 2GIS
    # link (imported from 2GIS) have no Yandex identity to recover here.
    resolvable = [o for o in candidates if (o.yandex_url or o.normalized_url)]
    no_link = len(candidates) - len(resolvable)
    if not resolvable:
        print(f"  resolve-links: 0 of {len(candidates)} points have a Yandex link to resolve",
              file=sys.stderr)
        return set()

    http = requests.Session()
    http.headers.update({
        "User-Agent": settings.http_scrape_user_agent,
        "Accept-Language": "ru-RU,ru;q=0.9",
    })
    # Direct by default: a plain redirect resolution is light and works from this
    # IP with a small delay; the single residential proxy hangs ~30s/request, far
    # too slow for hundreds of links. --resolve-proxy opts into it anyway.
    pool = None
    if use_proxy:
        from app.scraper.proxy_pool import ProxyPool
        pool = ProxyPool(settings.proxy_pool)
        print(f"  resolve-links: routing through proxy pool ({len(pool)})", file=sys.stderr)

    link_pids: set = set()
    resolved = not_in_chain = failed = streak = 0
    for org in resolvable:
        pid = resolve_short_link(http, org.yandex_url or org.normalized_url, pool)
        time.sleep(delay)
        if pid is None:
            failed += 1
            streak += 1
            if streak >= _RESOLVE_ABORT_STREAK:
                print(f"  resolve-links: {streak} consecutive request failures — likely "
                      f"rate-limited, stopping (kept {len(link_pids)}).", file=sys.stderr)
                break
            continue
        streak = 0
        match = branch_by_pid.get(pid)
        if match is not None and pid not in matched_pids:
            match.organization = org
            match.method = "short_link"
            match.confidence = 1.0
            matched_pids.add(pid)
            link_pids.add(pid)
            resolved += 1
        else:
            not_in_chain += 1  # resolved, but its id is not a branch of this chain
    print(f"  resolve-links: matched {resolved} of {len(resolvable)} linked points "
          f"({not_in_chain} resolved-but-not-in-chain, {failed} request-failed, "
          f"{no_link} had no Yandex link)", file=sys.stderr)
    return link_pids


def _print_report(company_name: str, chain: CabinetChain, plan: SyncPlan) -> None:
    print(f"\n=== {company_name}  ← cabinet «{chain.name}» (chain {chain.tycoon_id}) ===",
          file=sys.stderr)
    print(f"  deactivate:     {len(plan.deactivate)}", file=sys.stderr)
    for org in plan.deactivate:
        print(f"    - {org.name}  (external_id={org.external_id})", file=sys.stderr)
    print(f"  update:         {len(plan.update)}", file=sys.stderr)
    for item in plan.update:
        fields = ", ".join(
            f"{f}: {old!r}→{new!r}" for f, (old, new) in item.changes.items()
        )
        print(f"    ~ {item.organization.name}  [{fields}]", file=sys.stderr)
    print(f"  new in cabinet: {len(plan.new_in_cabinet)} open, unmatched (report only)",
          file=sys.stderr)
    for branch in plan.new_in_cabinet:
        print(f"    + {branch.name}  {branch.address}  (permanent_id={branch.permanent_id})",
              file=sys.stderr)
    print(f"  skipped closed: {len(plan.skipped_closed)} closed & not ours (not pulled in)",
          file=sys.stderr)
    print(f"  ambiguous:      {len(plan.ambiguous)} (no external_id, left untouched)",
          file=sys.stderr)


def run(company_filter: str | None, apply: bool, delay: float,
        resolve_links: bool, resolve_proxy: bool) -> int:
    session, companies = _load_companies()
    try:
        cabinet = Cabinet(settings.yandex_storage_state_path, settings.sprav_page_timeout_ms)
    except ManualActionNeeded as exc:
        print(f"error: {exc}", file=sys.stderr)
        session.close()
        return EXIT_MANUAL

    status = EXIT_OK
    try:
        chains = cabinet.chains()
    except ManualActionNeeded as exc:
        print(f"error: {exc}", file=sys.stderr)
        cabinet.close()
        session.close()
        return EXIT_MANUAL

    # Several cabinet chains can share a display name (e.g. a small regional/.by
    # chain also named «Суши Мастер»). Each company must be synced by exactly ONE
    # chain — its largest — or a 3-branch namesake would see every other branch as
    # "absent" and wrongly deactivate it. Largest-first + a per-company guard.
    chains = sorted(chains, key=lambda c: c.branch_count, reverse=True)
    synced_company_ids: set = set()

    try:
        for chain in chains:
            company = _match_chain_to_company(chain, companies)
            if company is None:
                print(f"skip: cabinet «{chain.name}» — no matching company", file=sys.stderr)
                continue
            if company_filter and company.name != company_filter:
                continue
            if company.id in synced_company_ids:
                print(f"skip: cabinet «{chain.name}» (chain {chain.tycoon_id}, "
                      f"{chain.branch_count} branches) — «{company.name}» already synced "
                      f"by a larger chain", file=sys.stderr)
                continue

            try:
                branches, chain_name, total, complete = cabinet.branches(chain.tycoon_id, delay)
            except ManualActionNeeded as exc:
                print(f"error on «{chain.name}»: {exc}", file=sys.stderr)
                status = EXIT_MANUAL
                continue
            if not branches:
                print(f"skip: «{chain.name}» returned no branches", file=sys.stderr)
                continue
            print(f"chain «{chain_name}»: {len(branches)}/{total} branches"
                  f"{'' if complete else '  ⚠ INCOMPLETE'}", file=sys.stderr)
            synced_company_ids.add(company.id)
            # A partial branch read must never drive deactivations: absence from a
            # truncated list is not a removal. Updates/backfills stay safe.
            if not complete:
                print("  ⚠ branch list incomplete (throttled) — deactivation DISABLED for this "
                      "chain; re-run to finish. Updates/backfills still applied.", file=sys.stderr)
                status = EXIT_MANUAL

            orgs = list(company.branches)
            report = calibrate(branches, orgs)
            print(f"  address-fallback calibration: checked={report.checked} "
                  f"correct={report.correct} refused={report.refused} wrong={report.wrong}",
                  file=sys.stderr)
            # An untrustworthy fallback is not fatal: the permalink (external_id)
            # matches are always reliable, so fall back to permalink-only. Points
            # with no external_id then stay unmatched → the ambiguous bucket,
            # never wrongly deactivated.
            use_address = report.is_trustworthy
            if not use_address:
                print("  address fallback untrustworthy (>=1 wrong) — matching by "
                      "external_id only; unmatched points go to 'ambiguous'.",
                      file=sys.stderr)
            matches = match_branches(branches, orgs, address_fallback=use_address)

            # Third matching route (opt-in): for points that still have no
            # external_id and no address match (all our /maps/-/CODE imports),
            # resolve the short link to its real permanent_id and pair it with the
            # cabinet branch of that id. Exact, not fuzzy — the id either is a
            # branch of this chain or it isn't.
            link_pids: set = set()
            if resolve_links:
                link_pids = _resolve_link_matches(matches, orgs, delay, use_proxy=resolve_proxy)

            def resolve(branch):
                # Short-link matches already know the canonical url — no edit/main.
                if branch.permanent_id in link_pids:
                    return maps_url_for(branch.permanent_id)
                url = cabinet.maps_url(branch.permanent_id)
                time.sleep(delay)  # pause between per-point edit/main loads
                return url

            plan = build_plan(matches, orgs, resolve, allow_deactivation=complete)
            _print_report(company.name, chain, plan)

            if apply:
                counts = apply_plan(plan)
                session.commit()
                print(f"  applied: deactivated={counts['deactivated']} "
                      f"updated={counts['updated']} "
                      f"(skipped_closed={counts['skipped_closed']} not pulled)", file=sys.stderr)
            else:
                print("  dry-run (no changes written). Re-run with --apply to commit.",
                      file=sys.stderr)
    finally:
        cabinet.close()
        session.close()
    return status


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sync the Yandex cabinet point list into our DB.")
    parser.add_argument("--company", default=None, help="Limit to one company (exact name).")
    parser.add_argument("--apply", action="store_true", help="Write the changes (default: dry-run).")
    parser.add_argument("--delay", type=float, default=2.0,
                        help="Seconds between per-point loads and branch pages (default 2).")
    parser.add_argument("--resolve-links", action="store_true",
                        help="Also match no-external_id points by resolving their /maps/-/CODE "
                             "short link to a permanent_id (public Maps request per point).")
    parser.add_argument("--resolve-proxy", action="store_true",
                        help="Route --resolve-links requests through PROXY_POOL (slow: the single "
                             "residential proxy hangs ~30s/request). Default is a direct request.")
    args = parser.parse_args(argv)
    return run(args.company, args.apply, args.delay, args.resolve_links, args.resolve_proxy)


if __name__ == "__main__":
    raise SystemExit(main())
