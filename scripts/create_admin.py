# create_admin.py
# Bootstrap script to create the first (or an additional) user account
# directly against backend/auth/auth.db. There is no self-service signup
# endpoint by design (specs/authentication/requirements.md, Requirement
# 4.4) - the first admin has to come from somewhere outside the API, and
# subsequent accounts are created by an existing admin (via this script,
# until a dashboard "manage users" screen exists).
#
# Usage:
#   python scripts/create_admin.py --username alice --role admin
#   python scripts/create_admin.py --username bob --role viewer
#
# Prompts for a password interactively (not passed as a CLI arg, so it
# doesn't end up in shell history / process listings).

import argparse
import getpass
import os
import sys

_BACKEND_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "backend"))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from auth import service  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a PromptShield dashboard user account.")
    parser.add_argument("--username", required=True)
    parser.add_argument("--role", choices=["admin", "viewer"], default="admin")
    args = parser.parse_args()

    if service.get_user_by_username(args.username) is not None:
        print(f"Error: a user named {args.username!r} already exists.", file=sys.stderr)
        return 1

    password = getpass.getpass("Password: ")
    confirm = getpass.getpass("Confirm password: ")
    if password != confirm:
        print("Error: passwords did not match.", file=sys.stderr)
        return 1

    try:
        user = service.create_user(args.username, password, args.role)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    print(f"Created user {user.username!r} (id={user.id}, role={user.role}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
