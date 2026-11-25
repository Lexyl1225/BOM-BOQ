#!/usr/bin/env python3
"""
Create (or recover) an Administrator account from the server's command line.

Use this when the app is deployed with an empty database and nobody can sign in:
registering an Admin from the login page needs an existing Admin's credentials.

Usage
-----
  python create-admin.py                       Prompt for username and password
  python create-admin.py --username Admin      Prompt for the password only
  python create-admin.py --username Admin --reset
                                               Reset an existing account's password
                                               and make it an active Administrator

Non-interactive (e.g. CI): set BOM_ADMIN_PASSWORD in the environment instead of
being prompted. The password is never accepted as a command-line argument, so it
does not end up in shell history or the process list.

Inside Docker:
  docker compose exec bom python create-admin.py
"""

import argparse
import getpass
import os
import sys
from datetime import datetime
from pathlib import Path


def _read_password(username: str) -> str:
    from app.services.user_service import password_policy_error, PASSWORD_POLICY_TEXT

    env_pwd = os.getenv("BOM_ADMIN_PASSWORD")
    if env_pwd:
        err = password_policy_error(env_pwd, username)
        if err:
            sys.exit(f"✗ BOM_ADMIN_PASSWORD rejected: {err}")
        return env_pwd

    print(f"Password rules: {PASSWORD_POLICY_TEXT}")
    while True:
        pwd = getpass.getpass("Password: ")
        err = password_policy_error(pwd, username)
        if err:
            print(f"  ✗ {err}")
            continue
        if getpass.getpass("Confirm password: ") != pwd:
            print("  ✗ Passwords do not match.")
            continue
        return pwd


def main() -> None:
    parser = argparse.ArgumentParser(description="Create or recover an Administrator account.")
    parser.add_argument("--username", help="Administrator username (prompted if omitted)")
    parser.add_argument("--department", default="Administration",
                        help='Department for the account (default: "Administration")')
    parser.add_argument("--reset", action="store_true",
                        help="If the username exists, reset its password and make it an active Admin")
    args = parser.parse_args()

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from app.config import settings
    from app.database import init_db, SessionLocal
    from app.models import User
    from app.auth import get_password_hash
    from app.services.api_key_service import ensure_department

    init_db()  # creates the tables on a brand-new database

    username = (args.username or input("Admin username: ")).strip()
    if not username or len(username) > 50:
        sys.exit("✗ Username must be 1–50 characters.")

    with SessionLocal() as db:
        user = db.query(User).filter(User.username == username).first()
        if user and not args.reset:
            sys.exit(f'✗ User "{username}" already exists. Re-run with --reset to reset '
                     "its password and make it an Administrator.")

        password = _read_password(username)
        now = datetime.utcnow()

        if user is None:
            user = User(username=username, created_at=now, department=args.department.strip())
            db.add(user)
            action = "Created"
        else:
            action = "Reset"

        user.password = get_password_hash(password)
        user.role = "admin"
        user.is_active = True
        user.must_change_password = False
        # Marks the password as chosen, which also switches off the built-in test-password
        # fallbacks for this account and signs out any older sessions.
        user.password_changed_at = now
        user.updated_at = now
        db.commit()

        ensure_department(db, user.department)

    print(f'✓ {action} Administrator "{username}".')
    print(f"  Database: {settings.DATABASE_URL}")
    print("  Sign in at /login with this username and password.")


if __name__ == "__main__":
    main()
