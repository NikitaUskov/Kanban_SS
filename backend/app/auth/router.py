"""Authentication API routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.orm import Session

from app.auth.dependencies import CurrentUser
from app.auth.schemas import (
    ChangePasswordRequest,
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    TokenPair,
    UserPublic,
)
from app.auth.service import change_password, login, logout, refresh
from app.database import get_db
from app.schemas import MessageResponse

router = APIRouter(prefix="/auth", tags=["Авторизация"])
DbSession = Annotated[Session, Depends(get_db)]


def _client_ip(request: Request) -> str:
    cloudflare_ip = request.headers.get("CF-Connecting-IP")
    if cloudflare_ip:
        return cloudflare_ip.strip()[:64]
    return request.client.host if request.client else "unknown"


@router.post("/login", response_model=TokenPair)
def login_route(payload: LoginRequest, request: Request, db: DbSession) -> TokenPair:
    return login(db, payload.username, payload.password, _client_ip(request))


@router.post("/refresh", response_model=TokenPair)
def refresh_route(payload: RefreshRequest, db: DbSession) -> TokenPair:
    return refresh(db, payload.refresh_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout_route(payload: LogoutRequest, db: DbSession, _user: CurrentUser) -> Response:
    logout(db, payload.refresh_token)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=UserPublic)
def me_route(user: CurrentUser) -> UserPublic:
    return UserPublic.model_validate(user)


@router.post("/change-password", response_model=MessageResponse)
def change_password_route(
    payload: ChangePasswordRequest, db: DbSession, user: CurrentUser
) -> MessageResponse:
    change_password(db, user, payload.current_password, payload.new_password)
    return MessageResponse(message="Пароль изменён. Выполните вход повторно на других устройствах")

