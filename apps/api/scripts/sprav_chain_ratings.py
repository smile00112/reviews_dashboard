"""Collect a Sprav chain's branches and their weekly rating history.

Read-only. Browserless — the cabinet server-renders both pages, so this needs
the saved operator cookies but no Playwright.

Writes one JSON document for later processing (feed it to
``scripts.load_rating_snapshots``). Diagnostics go to stderr.

    python -m scripts.sprav_chain_ratings --chain 2082553 --company "Суши Мастер Россия"
    python -m scripts.sprav_chain_ratings --chain 2082553 --branches-only

Each record carries the branch, its rating history, and the organization it was
matched to (``org_id``/``match_method``/``match_confidence``). When ``--company``
is given, the address fallback is calibrated against the exactly-matched
branches first and **abandoned** if it produces even one wrong answer — see
``services/sprav_branch_match``.

Exit codes: 0 collected, 2 needs_manual_action (expired session / captcha),
1 error or nothing collected.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from app.core.config import settings
from app.scraper.yandex_sprav_chain import SpravChainReader
from app.services.sprav_branch_match import BranchMatch, calibrate, match_branches

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_MANUAL = 2


def _load_organizations(company_name: str):
    """Organizations of one company — the pool the branches are matched against."""
    from app.core.database import SessionLocal
    from app.models.company import Company
    from app.models.organization import Organization

    session = SessionLocal()
    try:
        company = session.query(Company).filter(Company.name == company_name).one_or_none()
        if company is None:
            return None, []
        orgs = session.query(Organization).filter(Organization.company_id == company.id).all()
        # Detach-safe: read the attributes we need before the session closes.
        for org in orgs:
            _ = org.id, org.name, org.city, org.external_id
        return company, orgs
    finally:
        session.close()


def build_document(chain_id: str, chain_name: str | None, matches: list[BranchMatch], histories: dict) -> dict:
    """Assemble the output document. Pure — takes already-collected data."""
    records = []
    for match in matches:
        branch = match.branch
        history = histories.get(branch.permanent_id)
        records.append(
            {
                **dataclasses.asdict(branch),
                "sprav_url": f"https://yandex.ru/sprav/{branch.permanent_id}/p/edit/rating-history/",
                "org_id": str(match.organization.id) if match.organization else None,
                "org_name": match.organization.name if match.organization else None,
                "match_method": match.method,
                "match_confidence": round(match.confidence, 2),
                "history": [
                    {"week": p.week.isoformat(), "rating": p.rating, "opponents": p.opponents}
                    for p in (history.history if history else [])
                ],
                "stars": history.stars if history else {},
                "card_strength": history.card_strength if history else None,
                "factors": history.factors if history else [],
                "history_error": None if history else "not_collected",
            }
        )
    return {
        "chain_id": chain_id,
        "chain_name": chain_name,
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "branches": len(records),
        "records": records,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Collect a Sprav chain's branches and rating history.")
    parser.add_argument("--chain", required=True, help="Chain id from /sprav/chain/<id>/branches.")
    parser.add_argument("--company", default=None, help="Company name to match branches against.")
    parser.add_argument("--out", default=None, help="Where to write the JSON.")
    parser.add_argument("--branches-only", action="store_true", help="Skip the per-branch rating history.")
    parser.add_argument("--delay", type=float, default=settings.http_scrape_delay_seconds,
                        help="Seconds between rating-history requests.")
    args = parser.parse_args(argv)

    out = Path(args.out or f".local/sprav-chain-{args.chain}.json")
    reader = SpravChainReader()

    listing = reader.list_branches(args.chain)
    if listing.error_code:
        print(f"error:   {listing.error_code}", file=sys.stderr)
        print(f"message: {listing.error_message}", file=sys.stderr)
        return EXIT_MANUAL if listing.needs_manual_action else EXIT_ERROR
    if not listing.branches:
        print("error:   no branches in the cabinet response", file=sys.stderr)
        return EXIT_ERROR
    print(f"chain {args.chain} ({listing.chain_name}): {len(listing.branches)}/{listing.total} branches",
          file=sys.stderr)

    # --- match against our organizations
    matches = [BranchMatch(b, None, None, 0.0) for b in listing.branches]
    if args.company:
        company, orgs = _load_organizations(args.company)
        if company is None:
            print(f"error:   no company named {args.company!r}", file=sys.stderr)
            return EXIT_ERROR
        report = calibrate(listing.branches, orgs)
        print(
            f"address-fallback calibration on {report.checked} known pairs: "
            f"correct={report.correct} refused={report.refused} wrong={report.wrong}",
            file=sys.stderr,
        )
        if not report.is_trustworthy:
            print("error:   address fallback produced wrong matches — refusing to use it", file=sys.stderr)
            return EXIT_ERROR
        matches = match_branches(listing.branches, orgs)
        matched = sum(1 for m in matches if m.organization)
        print(f"matched {matched}/{len(matches)} branches to organizations", file=sys.stderr)

    # --- per-branch rating history
    histories: dict = {}
    failures = 0
    if not args.branches_only:
        for i, branch in enumerate(listing.branches, 1):
            history, error = reader.rating_history(branch.permanent_id)
            if error == "session_expired":
                print("error:   session expired mid-run", file=sys.stderr)
                return EXIT_MANUAL
            if error:
                failures += 1
            else:
                histories[branch.permanent_id] = history
            if i % 20 == 0 or i == len(listing.branches):
                print(f"{i}/{len(listing.branches)} rating histories, {failures} failed", file=sys.stderr)
            time.sleep(args.delay)

    document = build_document(args.chain, listing.chain_name, matches, histories)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {document['branches']} branches ({failures} without history) to {out}", file=sys.stderr)
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
