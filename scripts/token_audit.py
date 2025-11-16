"""Inspect stored API tokens and highlight legacy entries."""

from __future__ import annotations

import argparse
import json
from typing import Any

from recozik_web.auth_store import get_token_repository
from recozik_web.config import get_settings
from recozik_web.token_utils import TOKEN_HASH_PREFIX, token_hint_from_stored


def build_report(database_url: str) -> list[dict[str, Any]]:
    """Return a summary of every stored token."""
    repo = get_token_repository(database_url)
    rows = repo.list_tokens()
    report: list[dict[str, Any]] = []
    for record in rows:
        status = "secure" if record.token.startswith(TOKEN_HASH_PREFIX) else "legacy"
        report.append(
            {
                "token_hint": token_hint_from_stored(record.token),
                "user_id": record.user_id,
                "display_name": record.display_name,
                "roles": list(record.roles),
                "allowed_features": list(record.allowed_features),
                "quota_limits": record.quota_limits,
                "status": status,
            }
        )
    return report


def main() -> None:
    """Parse CLI arguments and print the audit report."""
    parser = argparse.ArgumentParser(
        description="Audit the auth token database and report hashing status.",
    )
    parser.add_argument(
        "--database-url",
        help="Override the auth database URL (defaults to WebSettings).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Render the report as JSON for automation.",
    )
    args = parser.parse_args()

    settings = get_settings()
    database_url = args.database_url or settings.auth_database_url_resolved
    report = build_report(database_url)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return

    print(f"Audit target: {database_url}")
    if not report:
        print("No tokens found.")
        return

    secure = sum(1 for row in report if row["status"] == "secure")
    legacy = len(report) - secure
    for row in report:
        print(
            f"- {row['display_name']} ({row['user_id']}): hint={row['token_hint']}"
            f" status={row['status']} features={','.join(row['allowed_features']) or 'none'}"
        )

    if legacy:
        print(f"WARNING: {legacy} token(s) remain in legacy format.")
    else:
        print("All tokens use PBKDF2 hashing.")


if __name__ == "__main__":
    main()
