"""Verify and atomically restore a SQLite backup while backend is stopped."""

import argparse
import json
import os
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

from app.config import get_settings
from scripts.backup_db import database_path_from_url, sqlite_backup, verify_database


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backup", type=Path, required=True)
    parser.add_argument("--database-url", default=get_settings().database_url)
    parser.add_argument("--emergency-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        backup = args.backup.resolve()
        if not backup.is_file():
            raise FileNotFoundError(f"Backup не найден: {backup}")
        verification = verify_database(backup)
        database = database_path_from_url(args.database_url)
        database.parent.mkdir(parents=True, exist_ok=True)
        args.emergency_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(UTC).strftime("%Y-%m-%d_%H-%M-%S")
        emergency: Path | None = None
        if database.exists():
            emergency = args.emergency_dir.resolve() / f"kanban_before_restore_{stamp}.db"
            sqlite_backup(database, emergency)
            verify_database(emergency)

        temp_database = database.with_suffix(database.suffix + ".restore.tmp")
        temp_database.unlink(missing_ok=True)
        sqlite_backup(backup, temp_database)
        verify_database(temp_database)
        os.replace(temp_database, database)
        result = {
            "restored": True,
            "backup": str(backup),
            "database": str(database),
            "emergencyBackup": str(emergency) if emergency else None,
            "verification": verification,
        }
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(f"Restore failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

