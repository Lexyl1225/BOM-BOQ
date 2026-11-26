#!/usr/bin/env python3
"""
Automated Online SQLite Backup Script for BOM / BOQ Studio Pro
- Uses SQLite's native .backup() API (safe while the app is running)
- Runs PRAGMA integrity_check on the created backup before finalizing
- Retains the latest N backups (default: 30) and prunes older ones
"""

import argparse
import logging
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

DEFAULT_DATA_DIR = Path(os.getenv("BOM_DATA_DIR", "/home/ubuntu/docker-data/bom"))
DEFAULT_RETENTION = int(os.getenv("BACKUP_RETENTION_COUNT", "30"))


def run_backup(data_dir: Path, keep: int) -> Path:
    db_path = data_dir / "bom_system.db"
    backup_dir = data_dir / "backups" / "daily"
    backup_dir.mkdir(parents=True, exist_ok=True)

    if not db_path.is_file():
        raise FileNotFoundError(f"Source database not found: {db_path}")

    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    dst_path = backup_dir / f"bom_system_{stamp}.db"
    tmp_path = backup_dir / f".bom_system_{stamp}.db.tmp"

    try:
        src = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=30)
        dst = sqlite3.connect(str(tmp_path))
        with dst:
            src.backup(dst)
        src.close()

        # Verify backup integrity before promoting into place
        check = dst.execute("PRAGMA integrity_check").fetchall()
        doc_count = dst.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        user_count = dst.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        dst.close()

        if check != [("ok",)]:
            raise RuntimeError(f"Backup failed integrity_check: {check}")

        os.replace(tmp_path, dst_path)
        size_kb = dst_path.stat().st_size / 1024
        logging.info(
            "Backup verified OK: %s (%.1f KB, users=%d, documents=%d)",
            dst_path,
            size_kb,
            user_count,
            doc_count,
        )
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        raise

    # Retention cleanup
    backups = sorted(backup_dir.glob("bom_system_*.db"))
    if keep > 0 and len(backups) > keep:
        for old in backups[:-keep]:
            old.unlink(missing_ok=True)
            logging.info("Pruned old backup: %s", old.name)

    return dst_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Online SQLite backup for BOM Studio Pro")
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=DEFAULT_DATA_DIR,
        help=f"External BOM data directory (default: {DEFAULT_DATA_DIR})",
    )
    parser.add_argument(
        "--keep",
        type=int,
        default=DEFAULT_RETENTION,
        help=f"Number of daily backups to retain (default: {DEFAULT_RETENTION})",
    )
    args = parser.parse_args()

    log_dir = args.data_dir / "backups"
    log_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(log_dir / "backup.log"),
            logging.StreamHandler(sys.stdout),
        ],
    )

    try:
        run_backup(args.data_dir, args.keep)
        return 0
    except Exception as exc:
        logging.error("Backup failed: %s", exc, exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())