"""Card CRUD, subtasks, collaboration, notifications and optimistic locking."""

import re

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.access import require_board_access
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
from app.models import Board, BoardMember, Card, CardChecklistItem, CardComment, User
from app.notifications.service import add_notification
from app.timeutils import utcnow
from app.users.service import require_active_user

MENTION_RE = re.compile(r"(?<![\w@])@([a-z0-9._-]{3,80})", re.IGNORECASE)


def _card_load_options():
    return (
        joinedload(Card.created_by),
        joinedload(Card.updated_by),
        joinedload(Card.assignee),
        selectinload(Card.comments).joinedload(CardComment.author),
        selectinload(Card.checklist_items).joinedload(CardChecklistItem.completed_by),
        selectinload(Card.subtasks).joinedload(Card.created_by),
        selectinload(Card.subtasks).joinedload(Card.updated_by),
        selectinload(Card.subtasks).joinedload(Card.assignee),
        selectinload(Card.subtasks).selectinload(Card.comments),
        selectinload(Card.subtasks).selectinload(Card.checklist_items),
        selectinload(Card.subtasks).selectinload(Card.subtasks),
    )


def require_card(
    db: Session,
    card_id: str,
    *,
    allow_archived: bool = False,
    actor: User | None = None,
    minimum_role: str = "viewer",
) -> Card:
    card = db.scalar(select(Card).options(*_card_load_options()).where(Card.id == card_id))
    if card is None:
        raise AppError(404, "CARD_NOT_FOUND", "Карточка не найдена")
    if actor is not None:
        require_board_access(db, card.board_id, actor, minimum_role)
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


def _cards_in_column(db: Session, column_id: str, *, root_only: bool = False) -> list[Card]:
    statement = select(Card).where(Card.column_id == column_id, Card.archived_at.is_(None))
    if root_only:
        statement = statement.where(Card.parent_card_id.is_(None))
    return list(db.scalars(statement.order_by(Card.position, Card.id)).all())


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
    subtasks = sorted(
        [item for item in card.subtasks if item.archived_at is None],
        key=lambda item: (item.position, item.created_at, item.id),
    )
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
        subtasks=[CardResponse.model_validate(item) for item in subtasks],
    )


def _ensure_assignee_member(db: Session, board_id: str, user_id: str) -> User:
    user = require_active_user(db, user_id)
    if user.role not in {"owner", "admin"}:
        member = db.scalar(
            select(BoardMember).where(
                BoardMember.board_id == board_id, BoardMember.user_id == user_id
            )
        )
        if member is None:
            raise AppError(
                400, "ASSIGNEE_NOT_BOARD_MEMBER", "Ответственный не является участником доски"
            )
    return user


def _notify_assignment(db: Session, card: Card, actor: User) -> None:
    if card.assignee_user_id:
        add_notification(
            db,
            user_id=card.assignee_user_id,
            type="assignment",
            title="Вы назначены ответственным",
            message=f"Карточка «{card.title}» назначена вам",
            actor_user_id=actor.id,
            board_id=card.board_id,
            card_id=card.id,
        )


def _notify_mentions(db: Session, card: Card, actor: User, body: str) -> None:
    usernames = {match.lower() for match in MENTION_RE.findall(body)}
    if not usernames:
        return
    users = list(
        db.scalars(select(User).where(User.username.in_(usernames), User.is_active.is_(True))).all()
    )
    for user in users:
        if user.role not in {"owner", "admin"}:
            membership = db.scalar(
                select(BoardMember).where(
                    BoardMember.board_id == card.board_id, BoardMember.user_id == user.id
                )
            )
            if membership is None:
                continue
        add_notification(
            db,
            user_id=user.id,
            type="mention",
            title="Вас упомянули",
            message=f"{actor.display_name} упомянул вас в карточке «{card.title}»",
            actor_user_id=actor.id,
            board_id=card.board_id,
            card_id=card.id,
        )


def get_card(db: Session, card_id: str, actor: User) -> CardDetailResponse:
    require_card(db, card_id, actor=actor, minimum_role="viewer")
    return _card_detail(db, card_id)


def create_card(db: Session, board_id: str, payload: CardCreate, actor: User) -> CardResponse:
    request_id = str(payload.client_request_id) if payload.client_request_id else None
    with write_coordinator.write():
        try:
            earlier = find_idempotent(db, request_id, "card.created")
            if earlier and earlier.entity_id:
                return _card_response(db, earlier.entity_id)
            board = require_board(db, board_id, actor=actor, minimum_role="editor")
            column = require_column(db, str(payload.column_id))
            if column.board_id != board.id:
                raise AppError(400, "COLUMN_BOARD_MISMATCH", "Колонка не принадлежит этой доске")
            parent: Card | None = None
            if payload.parent_card_id:
                parent = require_card(
                    db, str(payload.parent_card_id), actor=actor, minimum_role="editor"
                )
                if parent.board_id != board.id:
                    raise AppError(
                        400,
                        "PARENT_BOARD_MISMATCH",
                        "Родительская карточка находится на другой доске",
                    )
                if parent.parent_card_id is not None:
                    raise AppError(
                        400, "SUBTASK_DEPTH_LIMIT", "Подзадача не может иметь собственные подзадачи"
                    )
            assignee_id = None
            if payload.assignee_user_id:
                assignee_id = _ensure_assignee_member(
                    db, board.id, str(payload.assignee_user_id)
                ).id
            if parent is None:
                ensure_wip_capacity(db, column)
            cards = _cards_in_column(db, column.id, root_only=parent is None)
            if parent is not None:
                cards = [item for item in parent.subtasks if item.archived_at is None]
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
                parent_card_id=parent.id if parent else None,
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
            if parent:
                _touch_card(parent, actor)
            _touch_board(board)
            add_activity(
                db,
                board_id=board.id,
                actor_user_id=actor.id,
                action="subtask.created" if parent else "card.created",
                entity_type="card",
                entity_id=card.id,
                summary=(
                    f"Создана подзадача «{card.title}»"
                    if parent
                    else f"Создана карточка «{card.title}»"
                ),
                details={
                    "columnId": column.id,
                    "position": index,
                    "assigneeUserId": assignee_id,
                    "parentCardId": card.parent_card_id,
                },
                client_request_id=request_id,
            )
            _notify_assignment(db, card, actor)
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
            card = require_card(db, card_id, actor=actor, minimum_role="editor")
            board = require_board(db, card.board_id, actor=actor, minimum_role="editor")
            _assert_card_version(card, payload.expected_version)
            changed: list[str] = []
            assignment_changed = False
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
                assignment_changed = True
            elif payload.assignee_user_id is not None:
                assignee = _ensure_assignee_member(db, board.id, str(payload.assignee_user_id))
                if assignee.id != card.assignee_user_id:
                    card.assignee_user_id = assignee.id
                    card.assignee = assignee
                    changed.append("ответственный")
                    assignment_changed = True
            if payload.completed is not None and payload.completed != (
                card.completed_at is not None
            ):
                card.completed_at = utcnow() if payload.completed else None
                changed.append("выполнение")
            if not changed:
                raise AppError(400, "NO_CHANGES", "Не переданы изменения карточки")
            _touch_card(card, actor)
            if card.parent:
                _touch_card(card.parent, actor)
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
            if assignment_changed:
                _notify_assignment(db, card, actor)
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
            card = require_card(db, card_id, actor=actor, minimum_role="editor")
            board = require_board(db, card.board_id, actor=actor, minimum_role="editor")
            _assert_card_version(card, payload.expected_version)
            target = require_column(db, str(payload.target_column_id))
            if target.board_id != board.id:
                raise AppError(400, "COLUMN_BOARD_MISMATCH", "Целевая колонка не принадлежит доске")
            source_id = card.column_id
            if card.parent_card_id is None and target.id != source_id:
                ensure_wip_capacity(db, target)
            source_cards = [
                item
                for item in _cards_in_column(db, source_id, root_only=card.parent_card_id is None)
                if item.id != card.id
            ]
            target_cards = (
                source_cards
                if target.id == source_id
                else _cards_in_column(db, target.id, root_only=card.parent_card_id is None)
            )
            if card.parent_card_id is not None:
                siblings = [
                    item
                    for item in card.parent.subtasks
                    if item.archived_at is None and item.id != card.id
                ]
                source_cards = siblings
                target_cards = siblings
            target_index = min(payload.target_index, len(target_cards))
            target_cards.insert(target_index, card)
            now = utcnow()
            for position, item in enumerate(source_cards):
                if target.id != source_id and item.position != position:
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
            _touch_board(board)
            add_activity(
                db,
                board_id=board.id,
                actor_user_id=actor.id,
                action="card.moved",
                entity_type="card",
                entity_id=card.id,
                summary=f"Карточка «{card.title}» перемещена в «{target.title}»",
                details={
                    "sourceColumnId": source_id,
                    "targetColumnId": target.id,
                    "targetIndex": target_index,
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
    card = require_card(db, card_id, actor=actor, minimum_role="editor")
    board = require_board(db, card.board_id, actor=actor, minimum_role="editor")
    _assert_card_version(card, payload.expected_version)
    now = utcnow()
    card.archived_at = now
    _touch_card(card, actor)
    for subtask in card.subtasks:
        if subtask.archived_at is None:
            subtask.archived_at = now
            _touch_card(subtask, actor)
    siblings = [
        item
        for item in _cards_in_column(db, card.column_id, root_only=card.parent_card_id is None)
        if item.id != card.id
    ]
    for position, item in enumerate(siblings):
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
        client_request_id=str(payload.client_request_id) if payload.client_request_id else None,
    )
    db.commit()
    return _card_response(db, card.id)


def restore_card(db: Session, card_id: str, payload: CardRestore, actor: User) -> CardResponse:
    card = require_card(db, card_id, allow_archived=True, actor=actor, minimum_role="editor")
    if card.archived_at is None:
        raise AppError(409, "CARD_NOT_ARCHIVED", "Карточка не находится в архиве")
    board = require_board(db, card.board_id, actor=actor, minimum_role="editor")
    _assert_card_version(card, payload.expected_version)
    target_id = str(payload.target_column_id) if payload.target_column_id else card.column_id
    target = require_column(db, target_id)
    if target.board_id != board.id:
        raise AppError(400, "COLUMN_BOARD_MISMATCH", "Целевая колонка не принадлежит доске")
    if card.parent_card_id is None:
        ensure_wip_capacity(db, target)
    cards = _cards_in_column(db, target.id, root_only=card.parent_card_id is None)
    index = len(cards) if payload.target_index is None else min(payload.target_index, len(cards))
    cards.insert(index, card)
    now = utcnow()
    for position, item in enumerate(cards):
        if item.position != position or item.id == card.id:
            item.position = position
            item.version += 1
            item.updated_at = now
    card.column_id = target.id
    card.archived_at = None
    card.updated_by_user_id = actor.id
    _touch_board(board)
    add_activity(
        db,
        board_id=board.id,
        actor_user_id=actor.id,
        action="card.restored",
        entity_type="card",
        entity_id=card.id,
        summary=f"Карточка «{card.title}» восстановлена",
        client_request_id=str(payload.client_request_id) if payload.client_request_id else None,
    )
    db.commit()
    return _card_response(db, card.id)


def _require_comment(db: Session, comment_id: str, *, allow_deleted: bool = False) -> CardComment:
    item = db.scalar(
        select(CardComment)
        .options(joinedload(CardComment.author))
        .where(CardComment.id == comment_id)
    )
    if item is None or (item.deleted_at is not None and not allow_deleted):
        raise AppError(404, "COMMENT_NOT_FOUND", "Комментарий не найден")
    return item


def add_comment(db: Session, card_id: str, payload: CommentCreate, actor: User) -> CommentResponse:
    card = require_card(db, card_id, actor=actor, minimum_role="editor")
    board = require_board(db, card.board_id, actor=actor, minimum_role="editor")
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
        client_request_id=str(payload.client_request_id) if payload.client_request_id else None,
    )
    _notify_mentions(db, card, actor, payload.body)
    db.commit()
    comment.author = actor
    return CommentResponse.model_validate(comment)


def update_comment(
    db: Session, comment_id: str, payload: CommentUpdate, actor: User
) -> CommentResponse:
    comment = _require_comment(db, comment_id)
    if comment.author_user_id != actor.id:
        raise AppError(403, "COMMENT_FORBIDDEN", "Можно изменять только свои комментарии")
    if comment.version != payload.expected_version:
        raise AppError(409, "COMMENT_VERSION_CONFLICT", "Комментарий уже изменён")
    card = require_card(db, comment.card_id, actor=actor, minimum_role="editor")
    board = require_board(db, card.board_id, actor=actor, minimum_role="editor")
    comment.body = payload.body
    comment.version += 1
    comment.edited_at = utcnow()
    comment.updated_at = utcnow()
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
        client_request_id=str(payload.client_request_id) if payload.client_request_id else None,
    )
    _notify_mentions(db, card, actor, payload.body)
    db.commit()
    comment.author = actor
    return CommentResponse.model_validate(comment)


def delete_comment(
    db: Session, comment_id: str, payload: VersionedMutation, actor: User
) -> CommentResponse:
    request_id = str(payload.client_request_id) if payload.client_request_id else None
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
    card = require_card(db, comment.card_id, actor=actor, minimum_role="editor")
    board = require_board(db, card.board_id, actor=actor, minimum_role="editor")
    comment.deleted_at = utcnow()
    comment.version += 1
    comment.updated_at = utcnow()
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
    comment.author = actor
    return CommentResponse.model_validate(comment)


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
    card = require_card(db, card_id, actor=actor, minimum_role="editor")
    board = require_board(db, card.board_id, actor=actor, minimum_role="editor")
    items = _checklist_items(db, card.id)
    index = len(items) if payload.target_index is None else min(payload.target_index, len(items))
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
        client_request_id=str(payload.client_request_id) if payload.client_request_id else None,
    )
    db.commit()
    return ChecklistItemResponse.model_validate(_require_checklist_item(db, item.id))


def update_checklist_item(
    db: Session, item_id: str, payload: ChecklistItemUpdate, actor: User
) -> ChecklistItemResponse:
    item = _require_checklist_item(db, item_id)
    if item.version != payload.expected_version:
        raise AppError(409, "CHECKLIST_VERSION_CONFLICT", "Пункт чек-листа уже изменён")
    card = require_card(db, item.card_id, actor=actor, minimum_role="editor")
    board = require_board(db, card.board_id, actor=actor, minimum_role="editor")
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
        client_request_id=str(payload.client_request_id) if payload.client_request_id else None,
    )
    db.commit()
    return ChecklistItemResponse.model_validate(_require_checklist_item(db, item.id))


def move_checklist_item(
    db: Session, item_id: str, payload: ChecklistItemMove, actor: User
) -> ChecklistItemResponse:
    item = _require_checklist_item(db, item_id)
    if item.version != payload.expected_version:
        raise AppError(409, "CHECKLIST_VERSION_CONFLICT", "Пункт чек-листа уже изменён")
    card = require_card(db, item.card_id, actor=actor, minimum_role="editor")
    board = require_board(db, card.board_id, actor=actor, minimum_role="editor")
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
        client_request_id=str(payload.client_request_id) if payload.client_request_id else None,
    )
    db.commit()
    return ChecklistItemResponse.model_validate(_require_checklist_item(db, item.id))


def delete_checklist_item(
    db: Session, item_id: str, payload: VersionedMutation, actor: User
) -> None:
    request_id = str(payload.client_request_id) if payload.client_request_id else None
    if find_idempotent(db, request_id, "checklist.deleted"):
        return
    item = _require_checklist_item(db, item_id)
    if item.version != payload.expected_version:
        raise AppError(409, "CHECKLIST_VERSION_CONFLICT", "Пункт чек-листа уже изменён")
    card = require_card(db, item.card_id, actor=actor, minimum_role="editor")
    board = require_board(db, card.board_id, actor=actor, minimum_role="editor")
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
