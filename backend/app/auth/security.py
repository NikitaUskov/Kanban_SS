"""Argon2id password hashing and signed JWT helpers."""

from datetime import timedelta
from hashlib import sha256
from typing import Any, Literal
from uuid import uuid4

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from argon2.low_level import Type

from app.config import get_settings
from app.errors import AppError
from app.timeutils import utcnow

password_hasher = PasswordHasher(
    time_cost=3,
    memory_cost=65536,
    parallelism=4,
    hash_len=32,
    salt_len=16,
    type=Type.ID,
)


def hash_password(password: str) -> str:
    """Hash a password with Argon2id."""

    if len(password) < 8:
        raise ValueError("Пароль должен содержать не менее 8 символов")
    return password_hasher.hash(password)


def verify_password(password: str, encoded_hash: str) -> bool:
    """Verify a password without leaking comparison details."""

    try:
        return password_hasher.verify(encoded_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def password_needs_rehash(encoded_hash: str) -> bool:
    """Return whether current Argon2 parameters should replace an older hash."""

    try:
        return password_hasher.check_needs_rehash(encoded_hash)
    except InvalidHashError:
        return True


def create_token(subject: str, token_type: Literal["access", "refresh"]) -> tuple[str, int]:
    """Create a signed JWT and return it with its lifetime in seconds."""

    settings = get_settings()
    lifetime = (
        timedelta(hours=settings.access_token_expire_hours)
        if token_type == "access"
        else timedelta(days=settings.refresh_token_expire_days)
    )
    now = utcnow()
    payload = {
        "sub": subject,
        "type": token_type,
        "iat": now,
        "exp": now + lifetime,
        "jti": str(uuid4()),
        "iss": "kanban-board",
        "aud": "kanban-board-web",
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return token, int(lifetime.total_seconds())


def decode_token(token: str, expected_type: Literal["access", "refresh"]) -> dict[str, Any]:
    """Validate signature, expiry, audience, issuer and token type."""

    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            audience="kanban-board-web",
            issuer="kanban-board",
            options={"require": ["sub", "type", "iat", "exp", "jti"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise AppError(401, "TOKEN_EXPIRED", "Срок действия токена истёк") from exc
    except jwt.PyJWTError as exc:
        raise AppError(401, "TOKEN_INVALID", "Недействительный токен") from exc
    if payload.get("type") != expected_type:
        raise AppError(401, "TOKEN_TYPE_INVALID", "Использован неверный тип токена")
    return payload


def hash_token(token: str) -> str:
    """Store only a deterministic SHA-256 digest of refresh tokens."""

    return sha256(token.encode("utf-8")).hexdigest()
