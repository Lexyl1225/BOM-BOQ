#!/usr/bin/env python3
"""
API Key Generator

`generate_api_key()` is the single source of API keys for the application: the
server loads it from this file when it issues or regenerates a department key.

Usage
-----
  python api-key-gen.py                         Generate a key and write it to bom-secrets/.env
  python api-key-gen.py --department "Purchasing"  Generate (or replace) a department's key in the database
  python api-key-gen.py --all-missing           Issue keys for every department that has none
  python api-key-gen.py --list                  List departments with their masked keys
"""

import argparse
import os
import secrets
import sys
from pathlib import Path


def generate_api_key(length: int = 32) -> str:
    """Generate a cryptographically secure URL-safe API key."""
    return secrets.token_urlsafe(length)


def create_env_file(api_key: str, env_path: Path) -> None:
    """Create or overwrite the .env file with the API key."""
    env_path.parent.mkdir(parents=True, exist_ok=True)

    content = f"API_KEY={api_key}\n"

    with open(env_path, "w", encoding="utf-8") as f:
        f.write(content)

    # Restrict permissions so only the owner can read/write
    os.chmod(env_path, 0o600)


def _db_session():
    """Open an application database session (imports the app lazily)."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from app.database import SessionLocal, Base, engine
    from app import models  # noqa: F401  (register tables)
    Base.metadata.create_all(bind=engine)
    return SessionLocal()


def cmd_department(name: str) -> None:
    from app.services.api_key_service import ensure_department, get_department_by_slug, department_slug, regenerate_key
    with _db_session() as db:
        existed = get_department_by_slug(db, department_slug(name)) is not None
        dept = ensure_department(db, name)
        raw = regenerate_key(db, dept, None)
        verb = "Regenerated" if existed else "Generated"
        print(f"✓ {verb} API key for department: {dept.name}")
        print(f"  X-API-Key: {raw}")
        print("  Any previous key for this department no longer works.")


def cmd_all_missing() -> None:
    from app.models import Department
    from app.services.api_key_service import sync_departments, regenerate_key
    with _db_session() as db:
        added = sync_departments(db)
        issued = 0
        for dept in db.query(Department).all():
            if dept.api_key is None:
                regenerate_key(db, dept, None)
                issued += 1
        print(f"✓ Registered {added} new department(s); issued {issued} key(s) for departments without one.")
        print("  View or reveal keys on the API Keys page (/api_keys).")


def cmd_list() -> None:
    from app.services.api_key_service import describe_departments
    with _db_session() as db:
        rows = describe_departments(db)
        if not rows:
            print("No departments found.")
            return
        width = max(len(r["name"]) for r in rows)
        for r in rows:
            status = "no key" if not r["has_key"] else ("active" if r["is_active"] else "deactivated")
            print(f"  {r['name']:<{width}}  {r['masked_key'] or '-':<24}  {status}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate API keys for BOM / BOQ Studio Pro.")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--department", metavar="NAME", help="generate or replace the key for a department")
    group.add_argument("--all-missing", action="store_true", help="issue keys for departments that have none")
    group.add_argument("--list", action="store_true", help="list departments and their masked keys")
    args = parser.parse_args()

    if args.department:
        return cmd_department(args.department)
    if args.all_missing:
        return cmd_all_missing()
    if args.list:
        return cmd_list()

    # Default: original behaviour — write a standalone key to bom-secrets/.env
    script_dir = Path(__file__).resolve().parent
    secrets_dir = script_dir / "bom-secrets"
    env_file = secrets_dir / ".env"

    api_key = generate_api_key()
    create_env_file(api_key, env_file)

    print(f"✓ API key generated and saved to: {env_file}")
    print(f"  API_KEY={api_key}")
    print("  File permissions set to 600 (owner read/write only)")


if __name__ == "__main__":
    main()
