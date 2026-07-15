"""Authorize the Yandex operator session and report the outcome.

Test/diagnostic command for the Sprav cabinet scraper. Deliberately does NOT
touch the database — it exercises only the login path and the storage-state file.

  python -m scripts.sprav_login           # opens a browser; operator signs in by hand
  python -m scripts.sprav_login --check   # only verify the saved session

Exit codes: 0 valid, 2 needs_manual_action, 1 missing/expired.
"""

from __future__ import annotations

import argparse
import sys

from app.core.config import settings
from app.models.enums import SessionStatus
from app.scraper.yandex_auth import YandexAuthScraper

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
    parser = argparse.ArgumentParser(description="Authorize / check the Yandex operator session.")
    parser.add_argument("--check", action="store_true", help="Only check the saved session, do not log in.")
    args = parser.parse_args(argv)

    path = settings.yandex_storage_state_path
    scraper = YandexAuthScraper()

    if args.check:
        status = scraper.check_session(path)
        message = "checked saved session"
    else:
        print("Opening Yandex Passport — sign in by hand in the browser window.", file=sys.stderr)
        print("Waiting for the session cookie…", file=sys.stderr)
        status, message = scraper.login_manual(path)

    # Never print the storage-state contents — only its path.
    print(f"status:  {status.value}")
    print(f"message: {message}")
    print(f"session: {path}")

    return exit_code_for(status)


if __name__ == "__main__":
    raise SystemExit(main())
