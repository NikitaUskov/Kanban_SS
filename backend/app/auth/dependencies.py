"""FastAPI dependencies for active authenticated users."""

from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.security import decode_token
from app.database import get_db
from app.errors import AppError
from app.models import User

bearer = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    """Resolve a valid access token to an active user."""

    if credentials is None or credentials.scheme.lower() != "bearer":
        raise AppError(401, "AUTH_REQUIRED", "Требуется авторизация")
    payload = decode_token(credentials.credentials, "access")
    user = db.scalar(select(User).where(User.id == str(payload["sub"])))
    if user is None:
        raise AppError(401, "USER_NOT_FOUND", "Учётная запись не найдена")
    if not user.is_active:
        raise AppError(403, "USER_DISABLED", "Учётная запись отключена")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
