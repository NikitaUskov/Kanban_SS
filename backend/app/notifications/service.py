"""Creation and delivery of internal notifications."""

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, joinedload

from app.models import Notification, User
from app.timeutils import utcnow


def add_notification(
    db: Session,
    *,
    user_id: str,
    type: str,
    title: str,
    message: str,
    actor_user_id: str | None = None,
    board_id: str | None = None,
    card_id: str | None = None,
) -> Notification | None:
    if actor_user_id and actor_user_id == user_id:
        return None
    item = Notification(
        user_id=user_id,
        type=type,
        title=title,
        message=message,
        actor_user_id=actor_user_id,
        board_id=board_id,
        card_id=card_id,
    )
    db.add(item)
    return item


def list_notifications(
    db: Session, user: User, *, unread_only: bool, limit: int
) -> tuple[list[Notification], int]:
    statement = (
        select(Notification)
        .options(joinedload(Notification.actor))
        .where(Notification.user_id == user.id)
        .order_by(Notification.created_at.desc())
        .limit(limit)
    )
    if unread_only:
        statement = statement.where(Notification.read_at.is_(None))
    items = list(db.scalars(statement).all())
    unread = int(
        db.scalar(
            select(func.count(Notification.id)).where(
                Notification.user_id == user.id,
                Notification.read_at.is_(None),
            )
        )
        or 0
    )
    return items, unread


def mark_read(db: Session, notification_id: str, user: User) -> Notification:
    item = db.scalar(
        select(Notification)
        .options(joinedload(Notification.actor))
        .where(
            Notification.id == notification_id,
            Notification.user_id == user.id,
        )
    )
    if item is None:
        from app.errors import AppError

        raise AppError(404, "NOTIFICATION_NOT_FOUND", "Уведомление не найдено")
    if item.read_at is None:
        item.read_at = utcnow()
        db.commit()
        db.refresh(item)
    return item


def mark_all_read(db: Session, user: User) -> None:
    db.execute(
        update(Notification)
        .where(Notification.user_id == user.id, Notification.read_at.is_(None))
        .values(read_at=utcnow())
    )
    db.commit()
