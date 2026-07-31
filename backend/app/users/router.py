"""Authenticated public user directory routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.auth.dependencies import CurrentUser
from app.database import get_db
from app.users.schemas import UserPublic, UserPublicList
from app.users.service import list_users

router = APIRouter(prefix="/users", tags=["Пользователи"])
DbSession = Annotated[Session, Depends(get_db)]


@router.get("", response_model=UserPublicList)
def list_users_route(
    db: DbSession,
    _user: CurrentUser,
    active_only: bool = Query(default=True),
) -> UserPublicList:
    return UserPublicList(
        items=[UserPublic.model_validate(item) for item in list_users(db, active_only=active_only)]
    )
