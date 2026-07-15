"""Authorize the Yandex operator session and report the outcome.

Test/diagnostic command for the Sprav cabinet scraper. Deliberately does NOT
touch the database — it exercises only the login path and the storage-state file.

  python -m scripts.sprav_login             # headless auto-login with env creds
  python -m scripts.sprav_login --headed    # visible browser, operator does 2FA
  python -m scripts.sprav_login --check     # only verify the saved session

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
    parser.add_argument("--headed", action="store_true", help="Visible browser so the operator can pass 2FA/captcha.")
    args = parser.parse_args(argv)

    path = settings.yandex_storage_state_path
    scraper = YandexAuthScraper()

    if args.check:
        status = scraper.check_session(path)
        message = "checked saved session"
    else:
        status, message = scraper.login(
            settings.yandex_operator_login,
            settings.yandex_operator_password,
            path,
            headless=not args.headed,
        )

    # Never print the storage-state contents — only its path.
    print(f"status:  {status.value}")
    print(f"message: {message}")
    print(f"session: {path}")

    if status == SessionStatus.needs_manual_action and not args.headed:
        print("hint:    2FA/captcha likely — retry with: python -m scripts.sprav_login --headed", file=sys.stderr)

    return exit_code_for(status)


if __name__ == "__main__":
    raise SystemExit(main())
