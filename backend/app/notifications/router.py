"""Authenticated notification routes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.auth.dependencies import CurrentUser
from app.database import get_db
from app.notifications.schemas import NotificationList, NotificationResponse, UnreadCount
from app.notifications.service import list_notifications, mark_all_read, mark_read

router = APIRouter(prefix="/notifications", tags=["Уведомления"])
DbSession = Annotated[Session, Depends(get_db)]


@router.get("", response_model=NotificationList)
def list_route(
    db: DbSession,
    user: CurrentUser,
    unread_only: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
) -> NotificationList:
    items, unread = list_notifications(db, user, unread_only=unread_only, limit=limit)
    return NotificationList(
        items=[NotificationResponse.model_validate(item) for item in items],
        unread_count=unread,
    )


@router.get("/unread-count", response_model=UnreadCount)
def unread_count_route(db: DbSession, user: CurrentUser) -> UnreadCount:
    _, unread = list_notifications(db, user, unread_only=True, limit=1)
    return UnreadCount(unread_count=unread)


@router.post("/{notification_id}/read", response_model=NotificationResponse)
def mark_read_route(
    notification_id: UUID, db: DbSession, user: CurrentUser
) -> NotificationResponse:
    return NotificationResponse.model_validate(mark_read(db, str(notification_id), user))


@router.post("/read-all", status_code=status.HTTP_204_NO_CONTENT)
def mark_all_route(db: DbSession, user: CurrentUser) -> Response:
    mark_all_read(db, user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
