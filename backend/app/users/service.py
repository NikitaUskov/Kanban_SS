"""Local-only user management used by the administrative CLI."""

import re
from dataclasses import dataclass

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.auth.security import hash_password
from app.concurrency import write_coordinator
from app.errors import AppError
from app.models import RefreshToken, User
from app.timeutils import utcnow
from app.validation import clean_single_line

USERNAME_PATTERN = re.compile(r"^[a-z0-9._-]{3,80}$")


@dataclass(frozen=True)
class NewUser:
    username: str
    display_name: str
    password: str


def normalize_username(username: str) -> str:
    value = username.strip().lower()
    if not USERNAME_PATTERN.fullmatch(value):
        raise ValueError(
            "Имя пользователя: 3-80 символов; допустимы a-z, 0-9, точка, дефис и подчёркивание"
        )
    return value


def normalize_display_name(display_name: str) -> str:
    value = clean_single_line(display_name)
    if not 1 <= len(value) <= 120:
        raise ValueError("Отображаемое имя должно содержать от 1 до 120 символов")
    return value


def create_user(db: Session, data: NewUser) -> User:
    """Create one active account in a complete transaction."""

    username = normalize_username(data.username)
    display_name = normalize_display_name(data.display_name)
    encoded = hash_password(data.password)
    with write_coordinator.write():
        try:
            if db.scalar(select(User).where(User.username == username)) is not None:
                raise AppError(409, "USERNAME_EXISTS", "Такое имя пользователя уже существует")
            user = User(
                username=username,
                display_name=display_name,
                password_hash=encoded,
                is_active=True,
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            return user
        except Exception:
            db.rollback()
            raise


def create_users_batch(db: Session, items: list[NewUser]) -> list[User]:
    """Create a CSV batch atomically; no partial import is left on error."""

    normalized: list[tuple[str, str, str]] = []
    names: set[str] = set()
    for item in items:
        username = normalize_username(item.username)
        if username in names:
            raise ValueError(f"Имя {username} повторяется в CSV")
        names.add(username)
        normalized.append(
            (username, normalize_display_name(item.display_name), hash_password(item.password))
        )
    with write_coordinator.write():
        try:
            existing = set(db.scalars(select(User.username).where(User.username.in_(names))).all())
            if existing:
                raise AppError(
                    409,
                    "USERNAME_EXISTS",
                    f"Уже существуют: {', '.join(sorted(existing))}",
                )
            users = [
                User(
                    username=username,
                    display_name=display_name,
                    password_hash=password_hash,
                    is_active=True,
                )
                for username, display_name, password_hash in normalized
            ]
            db.add_all(users)
            db.commit()
            for user in users:
                db.refresh(user)
            return users
        except Exception:
            db.rollback()
            raise


def set_user_active(db: Session, username: str, is_active: bool) -> User:
    """Enable or disable an account; disabling revokes refresh sessions."""

    normalized = normalize_username(username)
    with write_coordinator.write():
        try:
            user = db.scalar(select(User).where(User.username == normalized))
            if user is None:
                raise AppError(404, "USER_NOT_FOUND", "Учётная запись не найдена")
            user.is_active = is_active
            user.updated_at = utcnow()
            if not is_active:
                db.execute(
                    update(RefreshToken)
                    .where(
                        RefreshToken.user_id == user.id,
                        RefreshToken.revoked_at.is_(None),
                    )
                    .values(revoked_at=utcnow())
                )
            db.commit()
            db.refresh(user)
            return user
        except Exception:
            db.rollback()
            raise


def reset_password(db: Session, username: str, new_password: str) -> User:
    """Replace a password and revoke every refresh session."""

    normalized = normalize_username(username)
    encoded = hash_password(new_password)
    with write_coordinator.write():
        try:
            user = db.scalar(select(User).where(User.username == normalized))
            if user is None:
                raise AppError(404, "USER_NOT_FOUND", "Учётная запись не найдена")
            user.password_hash = encoded
            user.updated_at = utcnow()
            db.execute(
                update(RefreshToken)
                .where(
                    RefreshToken.user_id == user.id,
                    RefreshToken.revoked_at.is_(None),
                )
                .values(revoked_at=utcnow())
            )
            db.commit()
            db.refresh(user)
            return user
        except Exception:
            db.rollback()
            raise


def require_active_user(db: Session, user_id: str) -> User:
    user = db.scalar(select(User).where(User.id == user_id))
    if user is None:
        raise AppError(404, "USER_NOT_FOUND", "Пользователь не найден")
    if not user.is_active:
        raise AppError(409, "USER_INACTIVE", "Нельзя назначить отключённого пользователя")
    return user


def list_users(db: Session, *, active_only: bool = False) -> list[User]:
    statement = select(User)
    if active_only:
        statement = statement.where(User.is_active.is_(True))
    return list(db.scalars(statement.order_by(User.display_name, User.username)).all())
