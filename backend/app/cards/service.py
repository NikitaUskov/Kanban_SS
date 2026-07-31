"""Card CRUD, collaboration, optimistic locking and WIP-aware movement."""

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.activity.service import add_activity, find_idempotent
from app.boards.service import require_board
from app.cards.schemas import (
    CardCreate,
    CardDetailResponse,
    CardMove,
    CardResponse,
    CardRestore,
    CardUpdate,
    ChecklistItemCreate,
    ChecklistItemMove,
    ChecklistItemResponse,
    ChecklistItemUpdate,
    CommentCreate,
    CommentResponse,
    CommentUpdate,
    VersionedMutation,
)
from app.columns.service import ensure_wip_capacity, require_column
from app.concurrency import write_coordinator
from app.errors import AppError
from app.models import Board, Card, CardChecklistItem, CardComment, User
from app.timeutils import utcnow
from app.users.service import require_active_user


def _card_load_options():
    return (
        joinedload(Card.created_by),
        joinedload(Card.updated_by),
        joinedload(Card.assignee),
        selectinload(Card.comments).joinedload(CardComment.author),
        selectinload(Card.checklist_items).joinedload(CardChecklistItem.completed_by),
    )


def require_card(db: Session, card_id: str, *, allow_archived: bool = False) -> Card:
    card = db.scalar(select(Card).options(*_card_load_options()).where(Card.id == card_id))
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


def _touch_card(card: Card, actor: User) -> None:
    card.version += 1
    card.updated_by_user_id = actor.id
    card.updated_at = utcnow()


def _cards_in_column(db: Session, column_id: str) -> list[Card]:
    return list(
        db.scalars(
            select(Card)
            .where(Card.column_id == column_id, Card.archived_at.is_(None))
            .order_by(Card.position, Card.id)
        ).all()
    )


def _checklist_items(db: Session, card_id: str) -> list[CardChecklistItem]:
    return list(
        db.scalars(
            select(CardChecklistItem)
            .where(CardChecklistItem.card_id == card_id)
            .order_by(CardChecklistItem.position, CardChecklistItem.id)
        ).all()
    )


def _card_response(db: Session, card_id: str) -> CardResponse:
    return CardResponse.model_validate(require_card(db, card_id, allow_archived=True))


def _card_detail(db: Session, card_id: str) -> CardDetailResponse:
    card = require_card(db, card_id, allow_archived=True)
    summary = CardResponse.model_validate(card)
    return CardDetailResponse(
        **summary.model_dump(),
        comments=[
            CommentResponse.model_validate(item)
            for item in card.comments
            if item.deleted_at is None
        ],
        checklist_items=[
            ChecklistItemResponse.model_validate(item) for item in card.checklist_items
        ],
    )


def get_card(db: Session, card_id: str) -> CardDetailResponse:
    return _card_detail(db, card_id)


def create_card(db: Session, board_id: str, payload: CardCreate, actor: User) -> CardResponse:
    request_id = str(payload.client_request_id) if payload.client_request_id else None
    with write_coordinator.write():
        try:
            earlier = find_idempotent(db, request_id, "card.created")
            if earlier and earlier.entity_id:
                return _card_response(db, earlier.entity_id)
            board = require_board(db, board_id)
            column = require_column(db, str(payload.column_id))
            if column.board_id != board.id:
                raise AppError(400, "COLUMN_BOARD_MISMATCH", "Колонка не принадлежит этой доске")
            assignee_id = None
            if payload.assignee_user_id:
                assignee_id = require_active_user(db, str(payload.assignee_user_id)).id
            ensure_wip_capacity(db, column)
            cards = _cards_in_column(db, column.id)
            index = (
                len(cards)
                if payload.target_index is None
                else min(payload.target_index, len(cards))
            )
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
                assignee_user_id=assignee_id,
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
                details={
                    "columnId": column.id,
                    "position": index,
                    "assigneeUserId": assignee_id,
                },
                client_request_id=request_id,
            )
            db.commit()
            return _card_response(db, card.id)
        except Exception:
            db.rollback()
            raise


def update_card(db: Session, card_id: str, payload: CardUpdate, actor: User) -> CardResponse:
    request_id = str(payload.client_request_id) if payload.client_request_id else None
    with write_coordinator.write():
        try:
            earlier = find_idempotent(db, request_id, "card.updated")
            if earlier and earlier.entity_id:
                return _card_response(db, earlier.entity_id)
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
            if payload.clear_assignee and card.assignee_user_id is not None:
                card.assignee_user_id = None
                card.assignee = None
                changed.append("ответственный")
            elif payload.assignee_user_id is not None:
                assignee = require_active_user(db, str(payload.assignee_user_id))
                if assignee.id != card.assignee_user_id:
                    card.assignee_user_id = assignee.id
                    card.assignee = assignee
                    changed.append("ответственный")
            if payload.completed is not None:
                currently_completed = card.completed_at is not None
                if payload.completed != currently_completed:
                    card.completed_at = utcnow() if payload.completed else None
                    changed.append("выполнение")
            if not changed:
                raise AppError(400, "NO_CHANGES", "Не переданы изменения карточки")
            _touch_card(card, actor)
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
            return _card_response(db, card.id)
        except Exception:
            db.rollback()
            raise


def move_card(db: Session, card_id: str, payload: CardMove, actor: User) -> CardResponse:
    request_id = str(payload.client_request_id) if payload.client_request_id else None
    with write_coordinator.write():
        try:
            earlier = find_idempotent(db, request_id, "card.moved")
            if earlier and earlier.entity_id:
                return _card_response(db, earlier.entity_id)
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
                ordered = [
                    item for item in _cards_in_column(db, source_column_id) if item.id != card.id
                ]
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
            return _card_response(db, card.id)
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
                return _card_response(db, earlier.entity_id)
            card = require_card(db, card_id)
            board = require_board(db, card.board_id)
            _assert_card_version(card, payload.expected_version)
            now = utcnow()
            card.archived_at = now
            card.version += 1
            card.updated_by_user_id = actor.id
            card.updated_at = now
            remaining = [
                item for item in _cards_in_column(db, card.column_id) if item.id != card.id
            ]
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
            return _card_response(db, card.id)
        except Exception:
            db.rollback()
            raise


def restore_card(db: Session, card_id: str, payload: CardRestore, actor: User) -> CardResponse:
    request_id = str(payload.client_request_id) if payload.client_request_id else None
    with write_coordinator.write():
        try:
            earlier = find_idempotent(db, request_id, "card.restored")
            if earlier and earlier.entity_id:
                return _card_response(db, earlier.entity_id)
            card = require_card(db, card_id, allow_archived=True)
            if card.archived_at is None:
                raise AppError(409, "CARD_NOT_ARCHIVED", "Карточка не находится в архиве")
            board = require_board(db, card.board_id)
            _assert_card_version(card, payload.expected_version)
            target_id = (
                str(payload.target_column_id) if payload.target_column_id else card.column_id
            )
            target = require_column(db, target_id)
            if target.board_id != board.id:
                raise AppError(
                    400,
                    "COLUMN_BOARD_MISMATCH",
                    "Целевая колонка не принадлежит доске карточки",
                )
            ensure_wip_capacity(db, target)
            target_cards = _cards_in_column(db, target.id)
            index = (
                len(target_cards)
                if payload.target_index is None
                else min(payload.target_index, len(target_cards))
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
            return _card_response(db, card.id)
        except Exception:
            db.rollback()
            raise


def _require_comment(db: Session, comment_id: str, *, allow_deleted: bool = False) -> CardComment:
    comment = db.scalar(
        select(CardComment)
        .options(joinedload(CardComment.author))
        .where(CardComment.id == comment_id)
    )
    if comment is None or (comment.deleted_at is not None and not allow_deleted):
        raise AppError(404, "COMMENT_NOT_FOUND", "Комментарий не найден")
    return comment


def add_comment(db: Session, card_id: str, payload: CommentCreate, actor: User) -> CommentResponse:
    request_id = str(payload.client_request_id) if payload.client_request_id else None
    with write_coordinator.write():
        try:
            earlier = find_idempotent(db, request_id, "comment.created")
            if earlier and earlier.entity_id:
                return CommentResponse.model_validate(_require_comment(db, earlier.entity_id))
            card = require_card(db, card_id)
            board = require_board(db, card.board_id)
            comment = CardComment(card_id=card.id, author_user_id=actor.id, body=payload.body)
            db.add(comment)
            db.flush()
            _touch_card(card, actor)
            _touch_board(board)
            add_activity(
                db,
                board_id=board.id,
                actor_user_id=actor.id,
                action="comment.created",
                entity_type="comment",
                entity_id=comment.id,
                summary=f"Добавлен комментарий к карточке «{card.title}»",
                details={"cardId": card.id},
                client_request_id=request_id,
            )
            db.commit()
            return CommentResponse.model_validate(_require_comment(db, comment.id))
        except Exception:
            db.rollback()
            raise


def update_comment(
    db: Session, comment_id: str, payload: CommentUpdate, actor: User
) -> CommentResponse:
    request_id = str(payload.client_request_id) if payload.client_request_id else None
    with write_coordinator.write():
        try:
            earlier = find_idempotent(db, request_id, "comment.updated")
            if earlier and earlier.entity_id:
                return CommentResponse.model_validate(_require_comment(db, earlier.entity_id))
            comment = _require_comment(db, comment_id)
            if comment.author_user_id != actor.id:
                raise AppError(403, "COMMENT_FORBIDDEN", "Можно изменять только свои комментарии")
            if comment.version != payload.expected_version:
                raise AppError(409, "COMMENT_VERSION_CONFLICT", "Комментарий уже изменён")
            if comment.body == payload.body:
                raise AppError(400, "NO_CHANGES", "Текст комментария не изменился")
            card = require_card(db, comment.card_id)
            board = require_board(db, card.board_id)
            now = utcnow()
            comment.body = payload.body
            comment.version += 1
            comment.edited_at = now
            comment.updated_at = now
            _touch_card(card, actor)
            _touch_board(board)
            add_activity(
                db,
                board_id=board.id,
                actor_user_id=actor.id,
                action="comment.updated",
                entity_type="comment",
                entity_id=comment.id,
                summary=f"Изменён комментарий к карточке «{card.title}»",
                details={"cardId": card.id},
                client_request_id=request_id,
            )
            db.commit()
            return CommentResponse.model_validate(_require_comment(db, comment.id))
        except Exception:
            db.rollback()
            raise


def delete_comment(
    db: Session, comment_id: str, payload: VersionedMutation, actor: User
) -> CommentResponse:
    request_id = str(payload.client_request_id) if payload.client_request_id else None
    with write_coordinator.write():
        try:
            earlier = find_idempotent(db, request_id, "comment.deleted")
            if earlier and earlier.entity_id:
                return CommentResponse.model_validate(
                    _require_comment(db, earlier.entity_id, allow_deleted=True)
                )
            comment = _require_comment(db, comment_id)
            if comment.author_user_id != actor.id:
                raise AppError(403, "COMMENT_FORBIDDEN", "Можно удалять только свои комментарии")
            if comment.version != payload.expected_version:
                raise AppError(409, "COMMENT_VERSION_CONFLICT", "Комментарий уже изменён")
            card = require_card(db, comment.card_id)
            board = require_board(db, card.board_id)
            now = utcnow()
            comment.deleted_at = now
            comment.version += 1
            comment.updated_at = now
            _touch_card(card, actor)
            _touch_board(board)
            add_activity(
                db,
                board_id=board.id,
                actor_user_id=actor.id,
                action="comment.deleted",
                entity_type="comment",
                entity_id=comment.id,
                summary=f"Удалён комментарий из карточки «{card.title}»",
                details={"cardId": card.id},
                client_request_id=request_id,
            )
            db.commit()
            db.refresh(comment)
            comment.author = actor
            return CommentResponse.model_validate(comment)
        except Exception:
            db.rollback()
            raise


def _require_checklist_item(db: Session, item_id: str) -> CardChecklistItem:
    item = db.scalar(
        select(CardChecklistItem)
        .options(joinedload(CardChecklistItem.completed_by))
        .where(CardChecklistItem.id == item_id)
    )
    if item is None:
        raise AppError(404, "CHECKLIST_ITEM_NOT_FOUND", "Пункт чек-листа не найден")
    return item


def add_checklist_item(
    db: Session, card_id: str, payload: ChecklistItemCreate, actor: User
) -> ChecklistItemResponse:
    request_id = str(payload.client_request_id) if payload.client_request_id else None
    with write_coordinator.write():
        try:
            earlier = find_idempotent(db, request_id, "checklist.created")
            if earlier and earlier.entity_id:
                return ChecklistItemResponse.model_validate(
                    _require_checklist_item(db, earlier.entity_id)
                )
            card = require_card(db, card_id)
            board = require_board(db, card.board_id)
            items = _checklist_items(db, card.id)
            index = (
                len(items)
                if payload.target_index is None
                else min(payload.target_index, len(items))
            )
            now = utcnow()
            for position, existing in enumerate(items):
                new_position = position if position < index else position + 1
                if existing.position != new_position:
                    existing.position = new_position
                    existing.version += 1
                    existing.updated_at = now
            item = CardChecklistItem(card_id=card.id, text=payload.text, position=index)
            db.add(item)
            db.flush()
            _touch_card(card, actor)
            _touch_board(board)
            add_activity(
                db,
                board_id=board.id,
                actor_user_id=actor.id,
                action="checklist.created",
                entity_type="checklist_item",
                entity_id=item.id,
                summary=f"Добавлен пункт чек-листа в карточку «{card.title}»",
                details={"cardId": card.id, "position": index},
                client_request_id=request_id,
            )
            db.commit()
            return ChecklistItemResponse.model_validate(_require_checklist_item(db, item.id))
        except Exception:
            db.rollback()
            raise


def update_checklist_item(
    db: Session, item_id: str, payload: ChecklistItemUpdate, actor: User
) -> ChecklistItemResponse:
    request_id = str(payload.client_request_id) if payload.client_request_id else None
    with write_coordinator.write():
        try:
            earlier = find_idempotent(db, request_id, "checklist.updated")
            if earlier and earlier.entity_id:
                return ChecklistItemResponse.model_validate(
                    _require_checklist_item(db, earlier.entity_id)
                )
            item = _require_checklist_item(db, item_id)
            if item.version != payload.expected_version:
                raise AppError(409, "CHECKLIST_VERSION_CONFLICT", "Пункт чек-листа уже изменён")
            card = require_card(db, item.card_id)
            board = require_board(db, card.board_id)
            changed: list[str] = []
            if payload.text is not None and payload.text != item.text:
                item.text = payload.text
                changed.append("текст")
            if payload.is_completed is not None and payload.is_completed != item.is_completed:
                item.is_completed = payload.is_completed
                item.completed_at = utcnow() if payload.is_completed else None
                item.completed_by_user_id = actor.id if payload.is_completed else None
                item.completed_by = actor if payload.is_completed else None
                changed.append("выполнение")
            if not changed:
                raise AppError(400, "NO_CHANGES", "Не переданы изменения пункта чек-листа")
            item.version += 1
            item.updated_at = utcnow()
            _touch_card(card, actor)
            _touch_board(board)
            add_activity(
                db,
                board_id=board.id,
                actor_user_id=actor.id,
                action="checklist.updated",
                entity_type="checklist_item",
                entity_id=item.id,
                summary=f"Изменён чек-лист карточки «{card.title}»",
                details={"cardId": card.id, "changedFields": changed},
                client_request_id=request_id,
            )
            db.commit()
            return ChecklistItemResponse.model_validate(_require_checklist_item(db, item.id))
        except Exception:
            db.rollback()
            raise


def move_checklist_item(
    db: Session, item_id: str, payload: ChecklistItemMove, actor: User
) -> ChecklistItemResponse:
    request_id = str(payload.client_request_id) if payload.client_request_id else None
    with write_coordinator.write():
        try:
            earlier = find_idempotent(db, request_id, "checklist.moved")
            if earlier and earlier.entity_id:
                return ChecklistItemResponse.model_validate(
                    _require_checklist_item(db, earlier.entity_id)
                )
            item = _require_checklist_item(db, item_id)
            if item.version != payload.expected_version:
                raise AppError(409, "CHECKLIST_VERSION_CONFLICT", "Пункт чек-листа уже изменён")
            card = require_card(db, item.card_id)
            board = require_board(db, card.board_id)
            ordered = [entry for entry in _checklist_items(db, card.id) if entry.id != item.id]
            target_index = min(payload.target_index, len(ordered))
            ordered.insert(target_index, item)
            now = utcnow()
            for position, entry in enumerate(ordered):
                if entry.position != position or entry.id == item.id:
                    entry.position = position
                    entry.version += 1
                    entry.updated_at = now
            _touch_card(card, actor)
            _touch_board(board)
            add_activity(
                db,
                board_id=board.id,
                actor_user_id=actor.id,
                action="checklist.moved",
                entity_type="checklist_item",
                entity_id=item.id,
                summary=f"Изменён порядок чек-листа карточки «{card.title}»",
                details={"cardId": card.id, "position": target_index},
                client_request_id=request_id,
            )
            db.commit()
            return ChecklistItemResponse.model_validate(_require_checklist_item(db, item.id))
        except Exception:
            db.rollback()
            raise


def delete_checklist_item(
    db: Session, item_id: str, payload: VersionedMutation, actor: User
) -> None:
    request_id = str(payload.client_request_id) if payload.client_request_id else None
    with write_coordinator.write():
        try:
            earlier = find_idempotent(db, request_id, "checklist.deleted")
            if earlier:
                return
            item = _require_checklist_item(db, item_id)
            if item.version != payload.expected_version:
                raise AppError(409, "CHECKLIST_VERSION_CONFLICT", "Пункт чек-листа уже изменён")
            card = require_card(db, item.card_id)
            board = require_board(db, card.board_id)
            remaining = [entry for entry in _checklist_items(db, card.id) if entry.id != item.id]
            db.delete(item)
            now = utcnow()
            for position, entry in enumerate(remaining):
                if entry.position != position:
                    entry.position = position
                    entry.version += 1
                    entry.updated_at = now
            _touch_card(card, actor)
            _touch_board(board)
            add_activity(
                db,
                board_id=board.id,
                actor_user_id=actor.id,
                action="checklist.deleted",
                entity_type="checklist_item",
                entity_id=item.id,
                summary=f"Удалён пункт чек-листа из карточки «{card.title}»",
                details={"cardId": card.id},
                client_request_id=request_id,
            )
            db.commit()
        except Exception:
            db.rollback()
            raise
