"""Column ordering, WIP enforcement and safe deletion logic."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.activity.service import add_activity, find_idempotent
from app.boards.service import require_board
from app.columns.schemas import (
    ColumnCreate,
    ColumnDelete,
    ColumnOrder,
    ColumnOrderResponse,
    ColumnResponse,
    ColumnUpdate,
)
from app.concurrency import write_coordinator
from app.errors import AppError
from app.models import Board, Card, Column, User
from app.timeutils import utcnow


def require_column(db: Session, column_id: str, *, allow_archived: bool = False) -> Column:
    column = db.scalar(select(Column).where(Column.id == column_id))
    if column is None:
        raise AppError(404, "COLUMN_NOT_FOUND", "Колонка не найдена")
    if column.archived_at is not None and not allow_archived:
        raise AppError(409, "COLUMN_ARCHIVED", "Колонка удалена")
    return column


def _assert_column_version(column: Column, expected_version: int) -> None:
    if column.version != expected_version:
        raise AppError(
            409,
            "COLUMN_VERSION_CONFLICT",
            "Колонка уже была изменена другим пользователем",
            {"entityId": column.id, "currentVersion": column.version},
        )


def ensure_wip_capacity(
    db: Session,
    column: Column,
    incoming_count: int = 1,
    *,
    exclude_card_ids: set[str] | None = None,
) -> None:
    """Reject a write that would exceed the target column's WIP limit."""

    if column.wip_limit is None:
        return
    statement = select(func.count(Card.id)).where(
        Card.column_id == column.id,
        Card.archived_at.is_(None),
    )
    if exclude_card_ids:
        statement = statement.where(Card.id.not_in(exclude_card_ids))
    active_count = int(db.scalar(statement) or 0)
    if active_count + incoming_count > column.wip_limit:
        raise AppError(
            409,
            "WIP_LIMIT_EXCEEDED",
            f"В колонке «{column.title}» достигнут WIP-лимит",
            {
                "columnId": column.id,
                "wipLimit": column.wip_limit,
                "currentCount": active_count,
                "incomingCount": incoming_count,
            },
        )


def _active_columns(db: Session, board_id: str) -> list[Column]:
    return list(
        db.scalars(
            select(Column)
            .where(Column.board_id == board_id, Column.archived_at.is_(None))
            .order_by(Column.position, Column.id)
        ).all()
    )


def _touch_board(board: Board) -> None:
    board.revision += 1
    board.version += 1
    board.updated_at = utcnow()


def _response(db: Session, column_id: str) -> ColumnResponse:
    return ColumnResponse.model_validate(require_column(db, column_id, allow_archived=True))


def create_column(db: Session, board_id: str, payload: ColumnCreate, actor: User) -> ColumnResponse:
    request_id = str(payload.client_request_id) if payload.client_request_id else None
    with write_coordinator.write():
        try:
            earlier = find_idempotent(db, request_id, "column.created")
            if earlier and earlier.entity_id:
                return _response(db, earlier.entity_id)
            board = require_board(db, board_id)
            columns = _active_columns(db, board_id)
            target_index = len(columns) if payload.target_index is None else payload.target_index
            target_index = min(target_index, len(columns))
            for index, existing in enumerate(columns):
                new_position = index if index < target_index else index + 1
                if existing.position != new_position:
                    existing.position = new_position
                    existing.version += 1
                    existing.updated_at = utcnow()
            column = Column(
                board_id=board.id,
                title=payload.title,
                position=target_index,
                wip_limit=payload.wip_limit,
                is_done=payload.is_done,
            )
            db.add(column)
            db.flush()
            _touch_board(board)
            add_activity(
                db,
                board_id=board.id,
                actor_user_id=actor.id,
                action="column.created",
                entity_type="column",
                entity_id=column.id,
                summary=f"Создана колонка «{column.title}»",
                client_request_id=request_id,
            )
            db.commit()
            return _response(db, column.id)
        except Exception:
            db.rollback()
            raise


def update_column(
    db: Session, column_id: str, payload: ColumnUpdate, actor: User
) -> ColumnResponse:
    request_id = str(payload.client_request_id) if payload.client_request_id else None
    with write_coordinator.write():
        try:
            earlier = find_idempotent(db, request_id, "column.updated")
            if earlier and earlier.entity_id:
                return _response(db, earlier.entity_id)
            column = require_column(db, column_id)
            board = require_board(db, column.board_id)
            _assert_column_version(column, payload.expected_version)
            changed: list[str] = []
            if payload.title is not None and payload.title != column.title:
                column.title = payload.title
                changed.append("название")
            if payload.clear_wip_limit and column.wip_limit is not None:
                column.wip_limit = None
                changed.append("WIP-лимит")
            elif payload.wip_limit is not None and payload.wip_limit != column.wip_limit:
                column.wip_limit = payload.wip_limit
                changed.append("WIP-лимит")
            if payload.is_done is not None and payload.is_done != column.is_done:
                column.is_done = payload.is_done
                changed.append("признак завершения")
            if not changed:
                raise AppError(400, "NO_CHANGES", "Не переданы изменения колонки")
            column.version += 1
            column.updated_at = utcnow()
            _touch_board(board)
            add_activity(
                db,
                board_id=board.id,
                actor_user_id=actor.id,
                action="column.updated",
                entity_type="column",
                entity_id=column.id,
                summary=f"Изменена колонка «{column.title}»",
                details={"changedFields": changed},
                client_request_id=request_id,
            )
            db.commit()
            return _response(db, column.id)
        except Exception:
            db.rollback()
            raise


def reorder_columns(
    db: Session, board_id: str, payload: ColumnOrder, actor: User
) -> ColumnOrderResponse:
    request_id = str(payload.client_request_id) if payload.client_request_id else None
    requested_ids = [str(item) for item in payload.column_ids]
    with write_coordinator.write():
        try:
            earlier = find_idempotent(db, request_id, "column.reordered")
            board = require_board(db, board_id)
            if earlier:
                columns = _active_columns(db, board.id)
                return ColumnOrderResponse(
                    board_id=board.id,
                    revision=board.revision,
                    version=board.version,
                    columns=[ColumnResponse.model_validate(item) for item in columns],
                )
            if board.version != payload.expected_board_version:
                raise AppError(
                    409,
                    "BOARD_VERSION_CONFLICT",
                    "Состав доски изменился до сохранения порядка колонок",
                    {
                        "entityId": board.id,
                        "currentVersion": board.version,
                        "currentRevision": board.revision,
                    },
                )
            columns = _active_columns(db, board.id)
            current_ids = {item.id for item in columns}
            if set(requested_ids) != current_ids or len(requested_ids) != len(columns):
                raise AppError(
                    409,
                    "COLUMN_ORDER_CONFLICT",
                    "Список колонок изменился. Загрузите доску заново",
                    {"currentColumnIds": [item.id for item in columns]},
                )
            by_id = {item.id: item for item in columns}
            for position, column_id in enumerate(requested_ids):
                column = by_id[column_id]
                if column.position != position:
                    column.position = position
                    column.version += 1
                    column.updated_at = utcnow()
            _touch_board(board)
            add_activity(
                db,
                board_id=board.id,
                actor_user_id=actor.id,
                action="column.reordered",
                entity_type="board",
                entity_id=board.id,
                summary="Изменён порядок колонок",
                details={"columnIds": requested_ids},
                client_request_id=request_id,
            )
            db.commit()
            ordered = _active_columns(db, board.id)
            return ColumnOrderResponse(
                board_id=board.id,
                revision=board.revision,
                version=board.version,
                columns=[ColumnResponse.model_validate(item) for item in ordered],
            )
        except Exception:
            db.rollback()
            raise


def delete_column(
    db: Session, column_id: str, payload: ColumnDelete, actor: User
) -> ColumnResponse:
    request_id = str(payload.client_request_id) if payload.client_request_id else None
    with write_coordinator.write():
        try:
            earlier = find_idempotent(db, request_id, "column.deleted")
            if earlier and earlier.entity_id:
                return _response(db, earlier.entity_id)
            column = require_column(db, column_id)
            board = require_board(db, column.board_id)
            _assert_column_version(column, payload.expected_version)
            cards = list(
                db.scalars(
                    select(Card)
                    .where(Card.column_id == column.id, Card.archived_at.is_(None))
                    .order_by(Card.position, Card.id)
                ).all()
            )
            if cards and payload.card_action is None:
                raise AppError(
                    409,
                    "COLUMN_NOT_EMPTY",
                    "Выберите перенос или архивацию карточек",
                    {"columnId": column.id, "activeCardCount": len(cards)},
                )
            now = utcnow()
            details: dict[str, object] = {"affectedCards": len(cards)}
            if cards and payload.card_action == "move":
                target = require_column(db, str(payload.target_column_id))
                if target.id == column.id or target.board_id != board.id:
                    raise AppError(
                        400,
                        "COLUMN_TARGET_INVALID",
                        "Целевая колонка должна быть другой активной колонкой этой доски",
                    )
                ensure_wip_capacity(db, target, len(cards))
                target_count = int(
                    db.scalar(
                        select(func.count(Card.id)).where(
                            Card.column_id == target.id,
                            Card.archived_at.is_(None),
                        )
                    )
                    or 0
                )
                for offset, card in enumerate(cards):
                    old_column_id = card.column_id
                    card.column_id = target.id
                    card.position = target_count + offset
                    card.version += 1
                    card.updated_by_user_id = actor.id
                    card.updated_at = now
                    add_activity(
                        db,
                        board_id=board.id,
                        actor_user_id=actor.id,
                        action="card.moved",
                        entity_type="card",
                        entity_id=card.id,
                        summary=f"Карточка «{card.title}» перенесена при удалении колонки",
                        details={
                            "fromColumnId": old_column_id,
                            "toColumnId": target.id,
                            "reason": "column_deleted",
                        },
                    )
                details["targetColumnId"] = target.id
            elif cards and payload.card_action == "archive":
                for card in cards:
                    card.archived_at = now
                    card.version += 1
                    card.updated_by_user_id = actor.id
                    card.updated_at = now
                    add_activity(
                        db,
                        board_id=board.id,
                        actor_user_id=actor.id,
                        action="card.archived",
                        entity_type="card",
                        entity_id=card.id,
                        summary=f"Карточка «{card.title}» архивирована при удалении колонки",
                        details={"reason": "column_deleted"},
                    )
            column.archived_at = now
            column.version += 1
            column.updated_at = now
            remaining = [item for item in _active_columns(db, board.id) if item.id != column.id]
            for position, item in enumerate(remaining):
                if item.position != position:
                    item.position = position
                    item.version += 1
                    item.updated_at = now
            _touch_board(board)
            add_activity(
                db,
                board_id=board.id,
                actor_user_id=actor.id,
                action="column.deleted",
                entity_type="column",
                entity_id=column.id,
                summary=f"Удалена колонка «{column.title}»",
                details=details,
                client_request_id=request_id,
            )
            db.commit()
            return _response(db, column.id)
        except Exception:
            db.rollback()
            raise
