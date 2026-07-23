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
import sys
import time
from dataclasses import dataclass

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
from app.services.sprav_sync import SyncPlan, apply_plan, build_plan

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_MANUAL = 2

MAX_BRANCH_PAGES = 100


class ManualActionNeeded(Exception):
    """A cabinet page demanded a human (expired session / captcha / passport)."""


@dataclass
class CabinetChain:
    tycoon_id: str
    permanent_id: str
    name: str


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
            if tycoon and pid and name and item.get("type") == "chain":
                result.append(CabinetChain(str(tycoon), str(pid), str(name)))
        return result

    def branches(self, tycoon_id: str, delay: float):
        """Every branch of a chain, paging the cabinet list (delay between pages)."""
        seen: set[str] = set()
        collected = []
        name = total = None
        for page in range(1, MAX_BRANCH_PAGES + 1):
            preload = self.preload(
                f"https://yandex.ru/sprav/chain/{tycoon_id}/branches?page={page}"
            )
            name = name or parse_chain_name(preload)
            total = parse_branch_total(preload) or total
            fresh = [b for b in parse_chain_branches(preload) if b.permanent_id not in seen]
            seen.update(b.permanent_id for b in fresh)
            collected.extend(fresh)
            if not fresh or (total is not None and len(collected) >= total):
                break
            time.sleep(delay)
        return collected, name, total

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
    print(f"  new in cabinet: {len(plan.new_in_cabinet)} (report only)", file=sys.stderr)
    for branch in plan.new_in_cabinet:
        print(f"    + {branch.name}  {branch.address}  (permanent_id={branch.permanent_id})",
              file=sys.stderr)
    print(f"  ambiguous:      {len(plan.ambiguous)} (no external_id, left untouched)",
          file=sys.stderr)


def run(company_filter: str | None, apply: bool, delay: float) -> int:
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

    try:
        for chain in chains:
            company = _match_chain_to_company(chain, companies)
            if company is None:
                print(f"skip: cabinet «{chain.name}» — no matching company", file=sys.stderr)
                continue
            if company_filter and company.name != company_filter:
                continue

            try:
                branches, chain_name, total = cabinet.branches(chain.tycoon_id, delay)
            except ManualActionNeeded as exc:
                print(f"error on «{chain.name}»: {exc}", file=sys.stderr)
                status = EXIT_MANUAL
                continue
            if not branches:
                print(f"skip: «{chain.name}» returned no branches", file=sys.stderr)
                continue
            print(f"chain «{chain_name}»: {len(branches)}/{total} branches", file=sys.stderr)

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

            def resolve(branch):
                url = cabinet.maps_url(branch.permanent_id)
                time.sleep(delay)  # pause between per-point edit/main loads
                return url

            plan = build_plan(matches, orgs, resolve)
            _print_report(company.name, chain, plan)

            if apply:
                counts = apply_plan(plan)
                session.commit()
                print(f"  applied: deactivated={counts['deactivated']} "
                      f"updated={counts['updated']}", file=sys.stderr)
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
    args = parser.parse_args(argv)
    return run(args.company, args.apply, args.delay)


if __name__ == "__main__":
    raise SystemExit(main())
