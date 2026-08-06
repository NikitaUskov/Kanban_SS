"""User directory, profile and administrative routes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.access import require_system_admin
from app.auth.dependencies import CurrentUser
from app.database import get_db
from app.users.schemas import (
    AdminUserList,
    AdminUserUpdate,
    ProfileUpdate,
    UserPublic,
    UserPublicList,
)
from app.users.service import admin_update_user, get_user, list_users, update_profile

router = APIRouter(tags=["Пользователи"])
DbSession = Annotated[Session, Depends(get_db)]


@router.get("/users", response_model=UserPublicList)
def list_users_route(
    db: DbSession,
    _user: CurrentUser,
    active_only: bool = Query(default=True),
    query: str | None = Query(default=None, max_length=120),
) -> UserPublicList:
    return UserPublicList(
        items=[
            UserPublic.model_validate(item)
            for item in list_users(db, active_only=active_only, query=query)
        ]
    )


@router.get("/profile", response_model=UserPublic)
def profile_route(user: CurrentUser) -> UserPublic:
    return UserPublic.model_validate(user)


@router.patch("/profile", response_model=UserPublic)
def update_profile_route(payload: ProfileUpdate, db: DbSession, user: CurrentUser) -> UserPublic:
    return UserPublic.model_validate(update_profile(db, user, payload))


@router.get("/admin/users", response_model=AdminUserList)
def admin_list_users_route(
    db: DbSession,
    user: CurrentUser,
    query: str | None = Query(default=None, max_length=120),
) -> AdminUserList:
    require_system_admin(user)
    return AdminUserList(
        items=[UserPublic.model_validate(item) for item in list_users(db, query=query)]
    )


@router.patch("/admin/users/{user_id}", response_model=UserPublic)
def admin_update_user_route(
    user_id: UUID,
    payload: AdminUserUpdate,
    db: DbSession,
    user: CurrentUser,
) -> UserPublic:
    target = get_user(db, str(user_id))
    return UserPublic.model_validate(admin_update_user(db, target, payload, user))
