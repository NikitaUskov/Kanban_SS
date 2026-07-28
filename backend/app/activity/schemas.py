"""Activity feed response schemas."""

from datetime import datetime
from typing import Any

from app.schemas import ORMModel


class ActivityActor(ORMModel):
    id: str
    username: str
    display_name: str


class ActivityItem(ORMModel):
    id: int
    board_id: str | None
    actor_user_id: str
    action: str
    entity_type: str
    entity_id: str | None
    summary: str
    details_json: dict[str, Any] | None
    created_at: datetime
    actor: ActivityActor


class ActivityPage(ORMModel):
    items: list[ActivityItem]
    next_before_id: int | None

