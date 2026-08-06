"""User creation, directory, profile and administrator operations."""

import re
from dataclasses import dataclass

from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from app.access import require_owner, require_system_admin
from app.auth.security import hash_password
from app.concurrency import write_coordinator
from app.errors import AppError
from app.models import RefreshToken, User
from app.timeutils import utcnow
from app.users.schemas import AdminUserUpdate, ProfileUpdate, clean_email
from app.validation import clean_single_line

USERNAME_PATTERN = re.compile(r"^[a-z0-9._-]{3,80}$")


@dataclass(frozen=True)
class NewUser:
    username: str
    display_name: str
    password: str
    email: str | None = None
    role: str = "member"


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


def _ensure_unique_email(
    db: Session, email: str | None, exclude_user_id: str | None = None
) -> None:
    if email is None:
        return
    statement = select(User.id).where(User.email_normalized == email)
    if exclude_user_id:
        statement = statement.where(User.id != exclude_user_id)
    if db.scalar(statement) is not None:
        raise AppError(409, "EMAIL_EXISTS", "Пользователь с таким email уже существует")


def create_user(db: Session, data: NewUser) -> User:
    username = normalize_username(data.username)
    display_name = normalize_display_name(data.display_name)
    email = clean_email(data.email)
    if data.role not in {"owner", "admin", "member"}:
        raise ValueError("Некорректная системная роль")
    encoded = hash_password(data.password)
    with write_coordinator.write():
        try:
            if db.scalar(select(User).where(User.username == username)) is not None:
                raise AppError(409, "USERNAME_EXISTS", "Такое имя пользователя уже существует")
            _ensure_unique_email(db, email)
            role = data.role
            if int(db.scalar(select(func.count(User.id))) or 0) == 0:
                role = "owner"
            user = User(
                username=username,
                display_name=display_name,
                email=email,
                email_normalized=email,
                email_verified_at=utcnow() if email else None,
                role=role,
                password_hash=encoded,
                is_active=True,
                notification_settings={},
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            return user
        except Exception:
            db.rollback()
            raise


def create_users_batch(db: Session, items: list[NewUser]) -> list[User]:
    """Create a CSV batch in one transaction."""

    prepared: list[tuple[str, str, str, str | None, str]] = []
    usernames: set[str] = set()
    emails: set[str] = set()
    for item in items:
        username = normalize_username(item.username)
        display_name = normalize_display_name(item.display_name)
        email = clean_email(item.email)
        if item.role not in {"owner", "admin", "member"}:
            raise ValueError("Некорректная системная роль")
        if username in usernames:
            raise AppError(409, "USERNAME_DUPLICATE", "Логин повторяется в CSV")
        if email and email in emails:
            raise AppError(409, "EMAIL_DUPLICATE", "Email повторяется в CSV")
        usernames.add(username)
        if email:
            emails.add(email)
        prepared.append((username, display_name, hash_password(item.password), email, item.role))

    with write_coordinator.write():
        try:
            if db.scalar(select(User.id).where(User.username.in_(usernames))) is not None:
                raise AppError(409, "USERNAME_EXISTS", "Один из логинов уже используется")
            if (
                emails
                and db.scalar(select(User.id).where(User.email_normalized.in_(emails))) is not None
            ):
                raise AppError(409, "EMAIL_EXISTS", "Один из email уже используется")
            existing_count = int(db.scalar(select(func.count(User.id))) or 0)
            created: list[User] = []
            for index, (username, display_name, password_hash, email, role) in enumerate(prepared):
                actual_role = "owner" if existing_count == 0 and index == 0 else role
                user = User(
                    username=username,
                    display_name=display_name,
                    email=email,
                    email_normalized=email,
                    email_verified_at=utcnow() if email else None,
                    role=actual_role,
                    password_hash=password_hash,
                    is_active=True,
                    notification_settings={},
                )
                db.add(user)
                created.append(user)
            db.commit()
            for user in created:
                db.refresh(user)
            return created
        except Exception:
            db.rollback()
            raise


def set_user_active(db: Session, username: str, is_active: bool) -> User:
    normalized = normalize_username(username)
    user = db.scalar(select(User).where(User.username == normalized))
    if user is None:
        raise AppError(404, "USER_NOT_FOUND", "Учётная запись не найдена")
    user.is_active = is_active
    user.updated_at = utcnow()
    if not is_active:
        db.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=utcnow())
        )
    db.commit()
    db.refresh(user)
    return user


def reset_password(db: Session, username: str, new_password: str) -> User:
    normalized = normalize_username(username)
    user = db.scalar(select(User).where(User.username == normalized))
    if user is None:
        raise AppError(404, "USER_NOT_FOUND", "Учётная запись не найдена")
    user.password_hash = hash_password(new_password)
    user.updated_at = utcnow()
    db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=utcnow())
    )
    db.commit()
    db.refresh(user)
    return user


def require_active_user(db: Session, user_id: str) -> User:
    user = db.scalar(select(User).where(User.id == user_id))
    if user is None:
        raise AppError(404, "USER_NOT_FOUND", "Пользователь не найден")
    if not user.is_active:
        raise AppError(409, "USER_INACTIVE", "Нельзя назначить отключённого пользователя")
    return user


def list_users(db: Session, *, active_only: bool = False, query: str | None = None) -> list[User]:
    statement = select(User)
    if active_only:
        statement = statement.where(User.is_active.is_(True))
    if query:
        like = f"%{query.strip().lower()}%"
        statement = statement.where(
            or_(
                func.lower(User.display_name).like(like),
                User.username.like(like),
                User.email_normalized.like(like),
            )
        )
    return list(db.scalars(statement.order_by(User.display_name, User.username)).all())


def update_profile(db: Session, user: User, payload: ProfileUpdate) -> User:
    changed = False
    if payload.display_name is not None and payload.display_name != user.display_name:
        user.display_name = normalize_display_name(payload.display_name)
        changed = True
    if payload.notification_settings is not None:
        allowed = {"assignment", "mention", "due_date"}
        user.notification_settings = {
            key: bool(value)
            for key, value in payload.notification_settings.items()
            if key in allowed
        }
        changed = True
    if not changed:
        raise AppError(400, "NO_CHANGES", "Не переданы изменения профиля")
    user.updated_at = utcnow()
    db.commit()
    db.refresh(user)
    return user


def admin_update_user(db: Session, target: User, payload: AdminUserUpdate, actor: User) -> User:
    require_system_admin(actor)
    removes_owner = target.role == "owner" and (
        (payload.role is not None and payload.role != "owner") or payload.is_active is False
    )
    if removes_owner:
        other_active_owners = int(
            db.scalar(
                select(func.count(User.id)).where(
                    User.role == "owner",
                    User.is_active.is_(True),
                    User.id != target.id,
                )
            )
            or 0
        )
        if other_active_owners == 0:
            raise AppError(
                409,
                "LAST_OWNER_REQUIRED",
                "Сначала назначьте другого активного владельца",
            )
    if target.role == "owner" and actor.role != "owner":
        raise AppError(403, "OWNER_PROTECTED", "Только владелец может изменять владельца")
    if payload.role == "owner":
        require_owner(actor)
    if target.id == actor.id and payload.is_active is False:
        raise AppError(400, "SELF_DISABLE_FORBIDDEN", "Нельзя отключить собственную учётную запись")
    if payload.display_name is not None:
        target.display_name = normalize_display_name(payload.display_name)
    if payload.clear_email:
        target.email = None
        target.email_normalized = None
        target.email_verified_at = None
    elif payload.email is not None:
        email = clean_email(payload.email)
        _ensure_unique_email(db, email, target.id)
        target.email = email
        target.email_normalized = email
        target.email_verified_at = utcnow()
    if payload.role is not None:
        target.role = payload.role
    if payload.is_active is not None:
        target.is_active = payload.is_active
        if not payload.is_active:
            db.execute(
                update(RefreshToken)
                .where(RefreshToken.user_id == target.id, RefreshToken.revoked_at.is_(None))
                .values(revoked_at=utcnow())
            )
    target.updated_at = utcnow()
    db.commit()
    db.refresh(target)
    return target


def get_user(db: Session, user_id: str) -> User:
    user = db.scalar(select(User).where(User.id == user_id))
    if user is None:
        raise AppError(404, "USER_NOT_FOUND", "Пользователь не найден")
    return user
