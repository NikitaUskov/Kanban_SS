"""Authentication, refresh rotation, logout and password changes."""

from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.auth.rate_limit import login_limiter
from app.auth.schemas import TokenPair
from app.auth.security import (
    create_token,
    decode_token,
    hash_password,
    hash_token,
    password_needs_rehash,
    verify_password,
)
from app.concurrency import write_coordinator
from app.config import get_settings
from app.errors import AppError
from app.models import RefreshToken, User
from app.timeutils import as_utc, utcnow


def _store_refresh(db: Session, user_id: str, token: str) -> RefreshToken:
    expires_at = utcnow() + timedelta(days=get_settings().refresh_token_expire_days)
    record = RefreshToken(
        user_id=user_id,
        token_hash=hash_token(token),
        expires_at=expires_at,
    )
    db.add(record)
    return record


def _issue_pair(db: Session, user: User) -> TokenPair:
    access_token, access_seconds = create_token(user.id, "access")
    refresh_token, refresh_seconds = create_token(user.id, "refresh")
    _store_refresh(db, user.id, refresh_token)
    return TokenPair(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=access_seconds,
        refresh_expires_in=refresh_seconds,
        user=user,
    )


def login(db: Session, username: str, password: str, ip_address: str) -> TokenPair:
    """Authenticate a user and create a persisted refresh session."""

    blocked, retry_after = login_limiter.is_blocked(ip_address, username)
    if blocked:
        raise AppError(
            429,
            "LOGIN_RATE_LIMITED",
            "Слишком много неудачных попыток входа",
            {"retryAfterSeconds": retry_after},
        )

    user = db.scalar(select(User).where(User.username == username.lower()))
    if user is None or not verify_password(password, user.password_hash):
        login_limiter.record_failure(ip_address, username)
        raise AppError(401, "INVALID_CREDENTIALS", "Неверное имя пользователя или пароль")
    if not user.is_active:
        login_limiter.record_failure(ip_address, username)
        raise AppError(403, "USER_DISABLED", "Учётная запись отключена")

    with write_coordinator.write():
        try:
            if password_needs_rehash(user.password_hash):
                user.password_hash = hash_password(password)
            user.last_login_at = utcnow()
            pair = _issue_pair(db, user)
            db.commit()
            db.refresh(user)
        except Exception:
            db.rollback()
            raise
    login_limiter.clear(ip_address, username)
    pair.user = user
    return pair


def refresh(db: Session, raw_refresh_token: str) -> TokenPair:
    """Rotate a refresh token and issue a new access/refresh pair."""

    payload = decode_token(raw_refresh_token, "refresh")
    digest = hash_token(raw_refresh_token)
    with write_coordinator.write():
        try:
            record = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == digest))
            if record is None or record.revoked_at is not None:
                raise AppError(401, "REFRESH_REVOKED", "Refresh token отозван или не найден")
            if as_utc(record.expires_at) <= utcnow():
                record.revoked_at = utcnow()
                db.commit()
                raise AppError(401, "REFRESH_EXPIRED", "Срок действия refresh token истёк")
            if record.user_id != str(payload["sub"]):
                raise AppError(401, "REFRESH_SUBJECT_MISMATCH", "Недействительный refresh token")
            user = db.scalar(select(User).where(User.id == record.user_id))
            if user is None:
                raise AppError(401, "USER_NOT_FOUND", "Учётная запись не найдена")
            if not user.is_active:
                raise AppError(403, "USER_DISABLED", "Учётная запись отключена")
            record.revoked_at = utcnow()
            pair = _issue_pair(db, user)
            db.commit()
            db.refresh(user)
            pair.user = user
            return pair
        except AppError:
            if db.in_transaction():
                db.rollback()
            raise
        except Exception:
            db.rollback()
            raise


def logout(db: Session, raw_refresh_token: str) -> None:
    """Idempotently revoke a supplied refresh token."""

    digest = hash_token(raw_refresh_token)
    with write_coordinator.write():
        try:
            record = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == digest))
            if record is not None and record.revoked_at is None:
                record.revoked_at = utcnow()
            db.commit()
        except Exception:
            db.rollback()
            raise


def change_password(db: Session, user: User, current_password: str, new_password: str) -> None:
    """Change the password and revoke all existing refresh sessions."""

    if not verify_password(current_password, user.password_hash):
        raise AppError(400, "CURRENT_PASSWORD_INVALID", "Текущий пароль указан неверно")
    if current_password == new_password:
        raise AppError(400, "PASSWORD_UNCHANGED", "Новый пароль должен отличаться от текущего")
    with write_coordinator.write():
        try:
            user.password_hash = hash_password(new_password)
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
        except Exception:
            db.rollback()
            raise
