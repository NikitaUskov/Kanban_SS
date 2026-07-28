"""Card CRUD, optimistic locking, ordering and WIP-aware movement."""

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.activity.service import add_activity, find_idempotent
from app.boards.service import require_board
from app.cards.schemas import (
    CardCreate,
    CardMove,
    CardResponse,
    CardRestore,
    CardUpdate,
    VersionedMutation,
)
from app.columns.service import ensure_wip_capacity, require_column
from app.concurrency import write_coordinator
from app.errors import AppError
from app.models import Board, Card, User
from app.timeutils import utcnow


def require_card(db: Session, card_id: str, *, allow_archived: bool = False) -> Card:
    card = db.scalar(
        select(Card)
        .options(joinedload(Card.created_by), joinedload(Card.updated_by))
        .where(Card.id == card_id)
    )
    if card is None:
        raise AppError(404, "CARD_NOT_FOUND", "Карточка не найдена")
    if card.archived_at is not None and not allow_archived:
        raise AppError(409, "CARD_ARCHIVED", "Карточка находится в архиве")
    return card


def _assert_card_version(card: Card, expected_version: int) -> None:
    if card.version != expected_version:
        raise AppError(
            409,
            "CARD_VERSION_CONFLICT",
            "Карточка уже была изменена другим пользователем",
            {
                "entityId": card.id,
                "currentVersion": card.version,
                "updatedByUserId": card.updated_by_user_id,
            },
        )


def _touch_board(board: Board) -> None:
    board.revision += 1
    board.version += 1
    board.updated_at = utcnow()


def _cards_in_column(db: Session, column_id: str) -> list[Card]:
    return list(
        db.scalars(
            select(Card)
            .where(Card.column_id == column_id, Card.archived_at.is_(None))
            .order_by(Card.position, Card.id)
        ).all()
    )


def _response(db: Session, card_id: str) -> CardResponse:
    return CardResponse.model_validate(require_card(db, card_id, allow_archived=True))


def get_card(db: Session, card_id: str) -> CardResponse:
    return _response(db, card_id)


def create_card(
    db: Session, board_id: str, payload: CardCreate, actor: User
) -> CardResponse:
    request_id = str(payload.client_request_id) if payload.client_request_id else None
    with write_coordinator.write():
        try:
            earlier = find_idempotent(db, request_id, "card.created")
            if earlier and earlier.entity_id:
                return _response(db, earlier.entity_id)
            board = require_board(db, board_id)
            column = require_column(db, str(payload.column_id))
            if column.board_id != board.id:
                raise AppError(400, "COLUMN_BOARD_MISMATCH", "Колонка не принадлежит этой доске")
            ensure_wip_capacity(db, column)
            cards = _cards_in_column(db, column.id)
            index = len(cards) if payload.target_index is None else min(payload.target_index, len(cards))
            now = utcnow()
            for position, existing in enumerate(cards):
                new_position = position if position < index else position + 1
                if existing.position != new_position:
                    existing.position = new_position
                    existing.version += 1
                    existing.updated_at = now
            card = Card(
                board_id=board.id,
                column_id=column.id,
                title=payload.title,
                description=payload.description,
                priority=payload.priority,
                due_date=payload.due_date,
                position=index,
                created_by_user_id=actor.id,
                updated_by_user_id=actor.id,
            )
            db.add(card)
            db.flush()
            _touch_board(board)
            add_activity(
                db,
                board_id=board.id,
                actor_user_id=actor.id,
                action="card.created",
                entity_type="card",
                entity_id=card.id,
                summary=f"Создана карточка «{card.title}»",
                details={"columnId": column.id, "position": index},
                client_request_id=request_id,
            )
            db.commit()
            return _response(db, card.id)
        except Exception:
            db.rollback()
            raise


def update_card(
    db: Session, card_id: str, payload: CardUpdate, actor: User
) -> CardResponse:
    request_id = str(payload.client_request_id) if payload.client_request_id else None
    with write_coordinator.write():
        try:
            earlier = find_idempotent(db, request_id, "card.updated")
            if earlier and earlier.entity_id:
                return _response(db, earlier.entity_id)
            card = require_card(db, card_id)
            board = require_board(db, card.board_id)
            _assert_card_version(card, payload.expected_version)
            changed: list[str] = []
            if payload.title is not None and payload.title != card.title:
                card.title = payload.title
                changed.append("название")
            if payload.clear_description and card.description is not None:
                card.description = None
                changed.append("описание")
            elif payload.description is not None and payload.description != card.description:
                card.description = payload.description
                changed.append("описание")
            if payload.priority is not None and payload.priority != card.priority:
                card.priority = payload.priority
                changed.append("приоритет")
            if payload.clear_due_date and card.due_date is not None:
                card.due_date = None
                changed.append("срок")
            elif payload.due_date is not None and payload.due_date != card.due_date:
                card.due_date = payload.due_date
                changed.append("срок")
            if not changed:
                raise AppError(400, "NO_CHANGES", "Не переданы изменения карточки")
            card.version += 1
            card.updated_by_user_id = actor.id
            card.updated_at = utcnow()
            _touch_board(board)
            add_activity(
                db,
                board_id=board.id,
                actor_user_id=actor.id,
                action="card.updated",
                entity_type="card",
                entity_id=card.id,
                summary=f"Изменена карточка «{card.title}»",
                details={"changedFields": changed},
                client_request_id=request_id,
            )
            db.commit()
            return _response(db, card.id)
        except Exception:
            db.rollback()
            raise


def move_card(db: Session, card_id: str, payload: CardMove, actor: User) -> CardResponse:
    request_id = str(payload.client_request_id) if payload.client_request_id else None
    with write_coordinator.write():
        try:
            earlier = find_idempotent(db, request_id, "card.moved")
            if earlier and earlier.entity_id:
                return _response(db, earlier.entity_id)
            card = require_card(db, card_id)
            board = require_board(db, card.board_id)
            _assert_card_version(card, payload.expected_version)
            target = require_column(db, str(payload.target_column_id))
            if target.board_id != board.id:
                raise AppError(
                    400,
                    "COLUMN_BOARD_MISMATCH",
                    "Целевая колонка не принадлежит доске карточки",
                )
            source_column_id = card.column_id
            old_position = card.position
            now = utcnow()
            if target.id == source_column_id:
                ordered = [item for item in _cards_in_column(db, source_column_id) if item.id != card.id]
                target_index = min(payload.target_index, len(ordered))
                ordered.insert(target_index, card)
                for position, item in enumerate(ordered):
                    if item.position != position or item.id == card.id:
                        item.position = position
                        item.version += 1
                        item.updated_at = now
                card.updated_by_user_id = actor.id
            else:
                ensure_wip_capacity(db, target)
                source_cards = [
                    item for item in _cards_in_column(db, source_column_id) if item.id != card.id
                ]
                target_cards = _cards_in_column(db, target.id)
                target_index = min(payload.target_index, len(target_cards))
                target_cards.insert(target_index, card)
                for position, item in enumerate(source_cards):
                    if item.position != position:
                        item.position = position
                        item.version += 1
                        item.updated_at = now
                for position, item in enumerate(target_cards):
                    if item.position != position or item.id == card.id:
                        item.position = position
                        item.version += 1
                        item.updated_at = now
                card.column_id = target.id
                card.updated_by_user_id = actor.id
            card.updated_at = now
            _touch_board(board)
            add_activity(
                db,
                board_id=board.id,
                actor_user_id=actor.id,
                action="card.moved",
                entity_type="card",
                entity_id=card.id,
                summary=f"Перемещена карточка «{card.title}»",
                details={
                    "fromColumnId": source_column_id,
                    "toColumnId": target.id,
                    "fromPosition": old_position,
                    "toPosition": card.position,
                },
                client_request_id=request_id,
            )
            db.commit()
            return _response(db, card.id)
        except Exception:
            db.rollback()
            raise


def archive_card(
    db: Session, card_id: str, payload: VersionedMutation, actor: User
) -> CardResponse:
    request_id = str(payload.client_request_id) if payload.client_request_id else None
    with write_coordinator.write():
        try:
            earlier = find_idempotent(db, request_id, "card.archived")
            if earlier and earlier.entity_id:
                return _response(db, earlier.entity_id)
            card = require_card(db, card_id)
            board = require_board(db, card.board_id)
            _assert_card_version(card, payload.expected_version)
            now = utcnow()
            card.archived_at = now
            card.version += 1
            card.updated_by_user_id = actor.id
            card.updated_at = now
            remaining = [item for item in _cards_in_column(db, card.column_id) if item.id != card.id]
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
                action="card.archived",
                entity_type="card",
                entity_id=card.id,
                summary=f"Карточка «{card.title}» перемещена в архив",
                client_request_id=request_id,
            )
            db.commit()
            return _response(db, card.id)
        except Exception:
            db.rollback()
            raise


def restore_card(
    db: Session, card_id: str, payload: CardRestore, actor: User
) -> CardResponse:
    request_id = str(payload.client_request_id) if payload.client_request_id else None
    with write_coordinator.write():
        try:
            earlier = find_idempotent(db, request_id, "card.restored")
            if earlier and earlier.entity_id:
                return _response(db, earlier.entity_id)
            card = require_card(db, card_id, allow_archived=True)
            if card.archived_at is None:
                raise AppError(409, "CARD_NOT_ARCHIVED", "Карточка не находится в архиве")
            board = require_board(db, card.board_id)
            _assert_card_version(card, payload.expected_version)
            target_id = str(payload.target_column_id) if payload.target_column_id else card.column_id
            target = require_column(db, target_id)
            if target.board_id != board.id:
                raise AppError(
                    400,
                    "COLUMN_BOARD_MISMATCH",
                    "Целевая колонка не принадлежит доске карточки",
                )
            ensure_wip_capacity(db, target)
            target_cards = _cards_in_column(db, target.id)
            index = len(target_cards) if payload.target_index is None else min(
                payload.target_index, len(target_cards)
            )
            now = utcnow()
            target_cards.insert(index, card)
            for position, item in enumerate(target_cards):
                if item.position != position or item.id == card.id:
                    item.position = position
                    item.version += 1
                    item.updated_at = now
            card.column_id = target.id
            card.archived_at = None
            card.updated_by_user_id = actor.id
            card.updated_at = now
            _touch_board(board)
            add_activity(
                db,
                board_id=board.id,
                actor_user_id=actor.id,
                action="card.restored",
                entity_type="card",
                entity_id=card.id,
                summary=f"Карточка «{card.title}» восстановлена",
                details={"columnId": target.id, "position": index},
                client_request_id=request_id,
            )
            db.commit()
            return _response(db, card.id)
        except Exception:
            db.rollback()
            raise

