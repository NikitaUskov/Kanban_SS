"""Notification API schemas."""

from datetime import datetime

from pydantic import BaseModel

from app.cards.schemas import UserBrief
from app.schemas import ORMModel


class NotificationResponse(ORMModel):
    id: str
    user_id: str
    type: str
    title: str
    message: str
    board_id: str | None
    card_id: str | None
    actor_user_id: str | None
    read_at: datetime | None
    created_at: datetime
    actor: UserBrief | None


class NotificationList(BaseModel):
    items: list[NotificationResponse]
    unread_count: int


class UnreadCount(BaseModel):
    unread_count: int
