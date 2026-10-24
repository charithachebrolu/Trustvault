"""Local operator commands for bootstrapping TrustVault administrators."""

from __future__ import annotations

import argparse
import sys

from .config import settings_from_env
from .database import connect, initialize_database, record_event
from .main import utc_now


def promote(email: str) -> int:
    settings = settings_from_env()
    initialize_database(settings.database_path)
    normalized_email = email.strip().lower()
    with connect(settings.database_path) as db:
        user = db.execute(
            "SELECT id, email, role FROM users WHERE email = ? COLLATE NOCASE", (normalized_email,),
        ).fetchone()
        if user is None:
            print(f"No account found for {normalized_email}. Register that account in TrustVault first.", file=sys.stderr)
            return 1
        if user["role"] == "admin":
            print(f"{user['email']} is already an administrator.")
            return 0
        db.execute("UPDATE users SET role = 'admin' WHERE id = ?", (user["id"],))
        record_event(
            db, event_type="account_promoted_to_admin", actor_id=user["id"],
            details="{\"source\":\"local_operator_command\"}", created_at=utc_now(),
        )
    print(f"Administrator access enabled for {user['email']}. Sign out and back in to see the Admin button.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Manage TrustVault administrator access")
    subparsers = parser.add_subparsers(dest="command", required=True)
    promote_parser = subparsers.add_parser("promote", help="Make an existing account an administrator")
    promote_parser.add_argument("email", help="Email of an account already registered in TrustVault")
    args = parser.parse_args()
    if args.command == "promote":
        return promote(args.email)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
