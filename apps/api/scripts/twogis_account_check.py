"""Check the saved 2GIS cabinet session and, if it works, print one organization.

Test/diagnostic command for feature 017. DB-free — it exercises only the storage-state
file and the live cabinet API, to confirm the imported Bearer token actually authenticates.

  python -m scripts.twogis_account_check           # check session + print one org
  python -m scripts.twogis_account_check --check    # check only, no org fetch

Exit codes: 0 valid, 2 needs_manual_action, 1 missing/expired. Never prints the token or
storage-state contents — only status, message, path, and the org's public fields.
"""

from __future__ import annotations

import argparse
import json
import sys

from app.core.config import settings
from app.models.enums import SessionStatus
from app.scraper.twogis_account import TwogisAccountScraper

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_MANUAL = 2


def exit_code_for(status: SessionStatus) -> int:
    if status == SessionStatus.valid:
        return EXIT_OK
    if status == SessionStatus.needs_manual_action:
        return EXIT_MANUAL
    return EXIT_ERROR


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check the saved 2GIS cabinet session.")
    parser.add_argument("--check", action="store_true", help="Only check the session; do not fetch an org.")
    args = parser.parse_args(argv)

    path = settings.twogis_storage_state_path
    scraper = TwogisAccountScraper()

    status, message = scraper.check_session(path)
    print(f"status:  {status.value}")
    print(f"message: {message}")
    print(f"session: {path}")

    if not args.check and status == SessionStatus.valid:
        orgs = scraper.list_orgs(path, limit=1)
        if orgs:
            print("org:")
            print(json.dumps(orgs[0], ensure_ascii=False, indent=2))
        else:
            print("org: (session valid but no organizations returned)", file=sys.stderr)

    return exit_code_for(status)


if __name__ == "__main__":
    raise SystemExit(main())
