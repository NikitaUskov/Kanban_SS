"""Create a consistent verified SQLite backup and apply retention rules."""

import argparse
import json
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.engine import make_url

from app import EXPECTED_ALEMBIC_REVISION
from app.config import get_settings

REQUIRED_TABLES = {
    "users",
    "refresh_tokens",
    "boards",
    "columns",
    "cards",
    "card_comments",
    "card_checklist_items",
    "activity_log",
    "user_invitations",
    "password_reset_tokens",
    "board_members",
    "notifications",
    "alembic_version",
}


def database_path_from_url(url_text: str) -> Path:
    url = make_url(url_text)
    if url.get_backend_name() != "sqlite" or not url.database or url.database == ":memory:":
        raise ValueError("Backup-скрипт поддерживает только файловую SQLite-базу")
    return Path(url.database).resolve()


def verify_database(path: Path) -> dict[str, object]:
    with sqlite3.connect(path) as connection:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise RuntimeError(f"PRAGMA integrity_check: {integrity}")
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        missing = sorted(REQUIRED_TABLES - tables)
        if missing:
            raise RuntimeError(f"Отсутствуют таблицы: {', '.join(missing)}")
        revision = connection.execute("SELECT version_num FROM alembic_version LIMIT 1").fetchone()
        revision_value = revision[0] if revision else None
        if revision_value != EXPECTED_ALEMBIC_REVISION:
            raise RuntimeError(
                f"Alembic revision {revision_value!r}, ожидалась {EXPECTED_ALEMBIC_REVISION}"
            )
        counts = {
            name: connection.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
            for name in (
                "users",
                "boards",
                "columns",
                "cards",
                "card_comments",
                "card_checklist_items",
                "activity_log",
                "user_invitations",
                "password_reset_tokens",
                "board_members",
                "notifications",
                "user_invitations",
                "password_reset_tokens",
                "board_members",
                "notifications",
            )
        }
    return {
        "verified": True,
        "integrityCheck": "ok",
        "alembicRevision": revision_value,
        "rowCounts": counts,
    }


def sqlite_backup(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with (
        sqlite3.connect(source, timeout=10) as source_db,
        sqlite3.connect(destination) as destination_db,
    ):
        source_db.backup(destination_db, pages=256, sleep=0.05)


def apply_retention(directory: Path, protected: Path) -> list[str]:
    candidates = sorted(directory.glob("kanban_*.db"), reverse=True)
    verified: list[Path] = []
    for candidate in candidates:
        metadata_path = candidate.with_suffix(".json")
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if metadata.get("verified") is True:
            verified.append(candidate)
    if protected not in verified:
        raise RuntimeError("Новая проверенная копия не найдена перед очисткой старых")

    keep = set(verified[:14])
    weekly_keys: set[tuple[int, int]] = set()
    for candidate in verified:
        stamp = datetime.fromtimestamp(candidate.stat().st_mtime, UTC)
        year, week, _weekday = stamp.isocalendar()
        key = (year, week)
        if key not in weekly_keys and len(weekly_keys) < 8:
            keep.add(candidate)
            weekly_keys.add(key)

    removed: list[str] = []
    for candidate in verified:
        if candidate in keep or candidate == protected:
            continue
        metadata_path = candidate.with_suffix(".json")
        candidate.unlink(missing_ok=True)
        metadata_path.unlink(missing_ok=True)
        removed.append(candidate.name)
    return removed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", default=get_settings().database_url)
    parser.add_argument("--backup-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        source = database_path_from_url(args.database_url)
        if not source.exists():
            raise FileNotFoundError(f"База не найдена: {source}")
        stamp = datetime.now(UTC).strftime("%Y-%m-%d_%H-%M-%S")
        destination = args.backup_dir.resolve() / f"kanban_{stamp}.db"
        sqlite_backup(source, destination)
        result = verify_database(destination)
        result.update(
            {
                "createdAt": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                "source": str(source),
                "backup": str(destination),
                "sizeBytes": destination.stat().st_size,
            }
        )
        destination.with_suffix(".json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        removed = apply_retention(args.backup_dir.resolve(), destination)
        result["removedByRetention"] = removed
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(f"Backup failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
