"""Atomic business activity journal helpers."""

from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.orm import Session, joinedload

from app.errors import AppError
from app.models import ActivityLog


def find_idempotent(
    db: Session, client_request_id: str | None, action: str | None = None
) -> ActivityLog | None:
    """Return an earlier mutation associated with the client request ID."""

    if not client_request_id:
        return None
    statement = select(ActivityLog).where(ActivityLog.client_request_id == client_request_id)
    item = db.scalar(statement)
    if item is not None and action is not None and item.action != action:
        raise AppError(
            409,
            "CLIENT_REQUEST_ID_REUSED",
            "client_request_id уже использован для другой операции",
            {"originalAction": item.action},
        )
    return item


def add_activity(
    db: Session,
    *,
    board_id: str | None,
    actor_user_id: str,
    action: str,
    entity_type: str,
    entity_id: str | None,
    summary: str,
    details: dict[str, Any] | None = None,
    client_request_id: str | None = None,
) -> ActivityLog:
    """Stage one journal row in the current transaction."""

    entry = ActivityLog(
        board_id=board_id,
        actor_user_id=actor_user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        summary=summary,
        details_json=details,
        client_request_id=client_request_id,
    )
    db.add(entry)
    return entry


def list_activity(
    db: Session, board_id: str, limit: int, before_id: int | None
) -> list[ActivityLog]:
    statement = (
        select(ActivityLog)
        .options(joinedload(ActivityLog.actor))
        .where(ActivityLog.board_id == board_id)
        .order_by(desc(ActivityLog.id))
        .limit(limit)
    )
    if before_id is not None:
        statement = statement.where(ActivityLog.id < before_id)
    return list(db.scalars(statement).all())
