"""Local CLI for creating, listing, enabling and resetting users."""

import argparse
import csv
import getpass
import logging
import sys
from pathlib import Path

from app.database import SessionLocal
from app.errors import AppError
from app.logging_config import configure_logging
from app.users.service import (
    NewUser,
    create_user,
    create_users_batch,
    list_users,
    reset_password,
    set_user_active,
)

logger = logging.getLogger("kanban.admin")


def read_password(prompt: str = "Пароль: ") -> str:
    first = getpass.getpass(prompt)
    second = getpass.getpass("Повторите пароль: ")
    if first != second:
        raise ValueError("Введённые пароли не совпадают")
    return first


def import_csv(path: Path) -> list[NewUser]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        required = {"username", "display_name", "password"}
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise ValueError("CSV должен содержать столбцы username, display_name, password")
        rows = [
            NewUser(
                username=(row.get("username") or ""),
                display_name=(row.get("display_name") or ""),
                password=(row.get("password") or ""),
            )
            for row in reader
        ]
    if not rows:
        raise ValueError("CSV не содержит пользователей")
    return rows


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Локальное управление пользователями Kanban")
    commands = parser.add_subparsers(dest="command", required=True)

    create = commands.add_parser("create", help="Создать пользователя")
    create.add_argument("username")
    create.add_argument("--display-name", required=True)

    commands.add_parser("list", help="Показать пользователей")

    for name in ("disable", "enable", "reset-password"):
        item = commands.add_parser(name)
        item.add_argument("username")

    batch = commands.add_parser("import-csv", help="Атомарно импортировать пользователей из CSV")
    batch.add_argument("file", type=Path)
    return parser


def main() -> int:
    configure_logging()
    args = build_parser().parse_args()
    try:
        with SessionLocal() as db:
            if args.command == "create":
                user = create_user(
                    db,
                    NewUser(
                        username=args.username,
                        display_name=args.display_name,
                        password=read_password(),
                    ),
                )
                logger.info("admin_action=user_created username=%s", user.username)
                print(f"Создан пользователь: {user.username} ({user.display_name})")
            elif args.command == "list":
                users = list_users(db)
                if not users:
                    print("Пользователей пока нет")
                for user in users:
                    state = "активен" if user.is_active else "отключён"
                    last_login = user.last_login_at.isoformat() if user.last_login_at else "-"
                    print(f"{user.username:24} {state:10} {user.display_name} | вход: {last_login}")
            elif args.command == "disable":
                user = set_user_active(db, args.username, False)
                logger.info("admin_action=user_disabled username=%s", user.username)
                print(f"Пользователь отключён: {user.username}")
            elif args.command == "enable":
                user = set_user_active(db, args.username, True)
                logger.info("admin_action=user_enabled username=%s", user.username)
                print(f"Пользователь включён: {user.username}")
            elif args.command == "reset-password":
                user = reset_password(db, args.username, read_password("Новый пароль: "))
                logger.info("admin_action=password_reset username=%s", user.username)
                print(f"Пароль изменён, старые refresh-сессии отозваны: {user.username}")
            elif args.command == "import-csv":
                users = create_users_batch(db, import_csv(args.file))
                for user in users:
                    logger.info("admin_action=user_created_batch username=%s", user.username)
                print(f"Создано пользователей: {len(users)}")
    except (AppError, ValueError, OSError) as exc:
        logger.error(
            "admin_action_failed command=%s error_type=%s", args.command, type(exc).__name__
        )
        print(f"Ошибка: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
