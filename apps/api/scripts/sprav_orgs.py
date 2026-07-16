"""Read the operator's organization list from the Yandex Business cabinet.

Read-only. Prints the organizations as JSON on stdout (pipeable to jq) and
writes the same JSON to a file. Diagnostics go to stderr.

  python -m scripts.sprav_orgs
  python -m scripts.sprav_orgs --pretty --out .local/sprav-orgs.json

Exit codes: 0 organizations found, 2 needs_manual_action, 1 error/empty.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from pathlib import Path

from app.core.config import settings
from app.scraper.yandex_sprav import SpravListResult, SpravOrg, YandexSpravScraper

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_MANUAL = 2


def orgs_to_json(orgs: list[SpravOrg], pretty: bool) -> str:
    payload = [dataclasses.asdict(org) for org in orgs]
    # ensure_ascii=False so Cyrillic names stay readable in the file and terminal.
    return json.dumps(payload, ensure_ascii=False, indent=2 if pretty else None)


def exit_code_for(result: SpravListResult) -> int:
    if result.needs_manual_action:
        return EXIT_MANUAL
    if result.error_code or not result.organizations:
        return EXIT_ERROR
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read the Sprav cabinet organization list.")
    parser.add_argument("--out", default=settings.sprav_orgs_output_path, help="Where to write the JSON.")
    parser.add_argument("--pretty", action="store_true", help="Indent the JSON.")
    args = parser.parse_args(argv)

    result = YandexSpravScraper().list_organizations(settings.yandex_storage_state_path)

    if result.needs_manual_action or result.error_code:
        print(f"error:   {result.error_code}", file=sys.stderr)
        print(f"message: {result.error_message}", file=sys.stderr)
        if result.debug_screenshot:
            print(f"debug:   {result.debug_screenshot}", file=sys.stderr)
        if result.debug_html:
            print(f"debug:   {result.debug_html}", file=sys.stderr)
        return exit_code_for(result)

    document = orgs_to_json(result.organizations, pretty=args.pretty)
    print(document)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(document, encoding="utf-8")
    print(f"wrote {len(result.organizations)} organizations to {out}", file=sys.stderr)

    return exit_code_for(result)


if __name__ == "__main__":
    raise SystemExit(main())
