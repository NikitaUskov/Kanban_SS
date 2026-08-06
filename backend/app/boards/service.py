"""Board business logic, access control, members and snapshot queries."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.access import get_board_role, is_system_admin, require_board_access, require_system_admin
from app.activity.service import add_activity, find_idempotent, list_activity
from app.boards.schemas import (
    BoardCreate,
    BoardDetail,
    BoardList,
    BoardListItem,
    BoardMemberResponse,
    BoardResponse,
    BoardSnapshot,
    BoardUpdate,
    BoardVersionMutation,
)
from app.cards.schemas import CardResponse, UserBrief
from app.columns.schemas import ColumnResponse
from app.concurrency import write_coordinator
from app.errors import AppError
from app.models import Board, BoardMember, Card, CardChecklistItem, CardComment, Column, User
from app.notifications.service import add_notification
from app.timeutils import utcnow
from app.users.service import require_active_user

DEFAULT_COLUMNS = (
    ("Бэклог", False),
    ("Запланировано", False),
    ("В работе", False),
    ("На проверке", False),
    ("Готово", True),
)


def require_board(
    db: Session,
    board_id: str,
    *,
    allow_archived: bool = False,
    load_creator: bool = False,
    actor: User | None = None,
    minimum_role: str = "viewer",
) -> Board:
    statement = select(Board).where(Board.id == board_id)
    if load_creator:
        statement = statement.options(joinedload(Board.creator))
    board = db.scalar(statement)
    if board is None:
        raise AppError(404, "BOARD_NOT_FOUND", "Доска не найдена")
    if actor is not None:
        require_board_access(db, board_id, actor, minimum_role)
    if board.archived_at is not None and not allow_archived:
        raise AppError(409, "BOARD_ARCHIVED", "Архивная доска недоступна для изменений")
    return board


def _assert_board_version(board: Board, expected_version: int) -> None:
    if board.version != expected_version:
        raise AppError(
            409,
            "BOARD_VERSION_CONFLICT",
            "Доска уже была изменена другим пользователем",
            {
                "entityId": board.id,
                "currentVersion": board.version,
                "currentRevision": board.revision,
            },
        )


def _detail(db: Session, board_id: str, actor: User) -> BoardDetail:
    board = require_board(
        db, board_id, allow_archived=True, load_creator=True, actor=actor, minimum_role="viewer"
    )
    data = BoardDetail.model_validate(board).model_dump()
    data["current_user_role"] = get_board_role(db, board.id, actor) or "viewer"
    return BoardDetail(**data)


def list_boards(db: Session, archived: bool, actor: User) -> BoardList:
    column_count = (
        select(func.count(Column.id))
        .where(Column.board_id == Board.id, Column.archived_at.is_(None))
        .correlate(Board)
        .scalar_subquery()
    )
    card_count = (
        select(func.count(Card.id))
        .where(
            Card.board_id == Board.id,
            Card.archived_at.is_(None),
            Card.parent_card_id.is_(None),
        )
        .correlate(Board)
        .scalar_subquery()
    )
    archive_filter = Board.archived_at.is_not(None) if archived else Board.archived_at.is_(None)
    statement = select(
        Board, column_count.label("column_count"), card_count.label("active_card_count")
    ).where(archive_filter)
    if not is_system_admin(actor):
        statement = statement.join(
            BoardMember,
            (BoardMember.board_id == Board.id) & (BoardMember.user_id == actor.id),
        )
    rows = db.execute(statement.order_by(Board.updated_at.desc(), Board.title.asc())).all()
    items: list[BoardListItem] = []
    for board, columns, cards in rows:
        data = BoardResponse.model_validate(board).model_dump()
        data["current_user_role"] = get_board_role(db, board.id, actor) or "viewer"
        items.append(
            BoardListItem(
                **data,
                column_count=int(columns or 0),
                active_card_count=int(cards or 0),
            )
        )
    return BoardList(items=items)


def get_board(db: Session, board_id: str, actor: User) -> BoardDetail:
    return _detail(db, board_id, actor)


def create_board(db: Session, payload: BoardCreate, actor: User) -> BoardDetail:
    require_system_admin(actor)
    request_id = str(payload.client_request_id) if payload.client_request_id else None
    with write_coordinator.write():
        try:
            earlier = find_idempotent(db, request_id, "board.created")
            if earlier and earlier.entity_id:
                return _detail(db, earlier.entity_id, actor)
            board = Board(
                title=payload.title, description=payload.description, created_by_user_id=actor.id
            )
            db.add(board)
            db.flush()
            db.add(
                BoardMember(
                    board_id=board.id, user_id=actor.id, role="admin", created_by_user_id=actor.id
                )
            )
            if payload.create_default_columns:
                for position, (title, is_done) in enumerate(DEFAULT_COLUMNS):
                    db.add(
                        Column(board_id=board.id, title=title, position=position, is_done=is_done)
                    )
            add_activity(
                db,
                board_id=board.id,
                actor_user_id=actor.id,
                action="board.created",
                entity_type="board",
                entity_id=board.id,
                summary=f"Создана доска «{board.title}»",
                details={"defaultColumns": payload.create_default_columns},
                client_request_id=request_id,
            )
            db.commit()
            return _detail(db, board.id, actor)
        except Exception:
            db.rollback()
            raise


def update_board(db: Session, board_id: str, payload: BoardUpdate, actor: User) -> BoardDetail:
    request_id = str(payload.client_request_id) if payload.client_request_id else None
    with write_coordinator.write():
        try:
            earlier = find_idempotent(db, request_id, "board.updated")
            if earlier and earlier.entity_id:
                return _detail(db, earlier.entity_id, actor)
            board = require_board(db, board_id, actor=actor, minimum_role="admin")
            _assert_board_version(board, payload.expected_version)
            changed: list[str] = []
            if payload.title is not None and payload.title != board.title:
                board.title = payload.title
                changed.append("название")
            if payload.clear_description and board.description is not None:
                board.description = None
                changed.append("описание")
            elif payload.description is not None and payload.description != board.description:
                board.description = payload.description
                changed.append("описание")
            if not changed:
                raise AppError(400, "NO_CHANGES", "Не переданы изменения доски")
            board.version += 1
            board.revision += 1
            board.updated_at = utcnow()
            add_activity(
                db,
                board_id=board.id,
                actor_user_id=actor.id,
                action="board.updated",
                entity_type="board",
                entity_id=board.id,
                summary=f"Изменены {', '.join(changed)} доски «{board.title}»",
                details={"changedFields": changed},
                client_request_id=request_id,
            )
            db.commit()
            return _detail(db, board.id, actor)
        except Exception:
            db.rollback()
            raise


def archive_board(
    db: Session, board_id: str, payload: BoardVersionMutation, actor: User
) -> BoardDetail:
    board = require_board(db, board_id, actor=actor, minimum_role="admin")
    _assert_board_version(board, payload.expected_version)
    board.archived_at = utcnow()
    board.version += 1
    board.revision += 1
    board.updated_at = utcnow()
    add_activity(
        db,
        board_id=board.id,
        actor_user_id=actor.id,
        action="board.archived",
        entity_type="board",
        entity_id=board.id,
        summary=f"Доска «{board.title}» перемещена в архив",
        client_request_id=str(payload.client_request_id) if payload.client_request_id else None,
    )
    db.commit()
    return _detail(db, board.id, actor)


def restore_board(
    db: Session, board_id: str, payload: BoardVersionMutation, actor: User
) -> BoardDetail:
    board = require_board(db, board_id, allow_archived=True, actor=actor, minimum_role="admin")
    if board.archived_at is None:
        raise AppError(409, "BOARD_NOT_ARCHIVED", "Доска не находится в архиве")
    _assert_board_version(board, payload.expected_version)
    board.archived_at = None
    board.version += 1
    board.revision += 1
    board.updated_at = utcnow()
    add_activity(
        db,
        board_id=board.id,
        actor_user_id=actor.id,
        action="board.restored",
        entity_type="board",
        entity_id=board.id,
        summary=f"Доска «{board.title}» восстановлена",
        client_request_id=str(payload.client_request_id) if payload.client_request_id else None,
    )
    db.commit()
    return _detail(db, board.id, actor)


def get_snapshot(db: Session, board_id: str, include_archived: bool, actor: User) -> BoardSnapshot:
    board = require_board(
        db, board_id, allow_archived=True, load_creator=True, actor=actor, minimum_role="viewer"
    )
    column_statement = (
        select(Column).where(Column.board_id == board_id).order_by(Column.position, Column.id)
    )
    card_statement = (
        select(Card)
        .options(
            joinedload(Card.created_by),
            joinedload(Card.updated_by),
            joinedload(Card.assignee),
            selectinload(Card.comments).joinedload(CardComment.author),
            selectinload(Card.checklist_items).joinedload(CardChecklistItem.completed_by),
            selectinload(Card.subtasks),
        )
        .where(Card.board_id == board_id, Card.parent_card_id.is_(None))
        .order_by(Card.column_id, Card.position, Card.id)
    )
    if not include_archived:
        column_statement = column_statement.where(Column.archived_at.is_(None))
        card_statement = card_statement.where(Card.archived_at.is_(None))
    columns = list(db.scalars(column_statement).all())
    cards = list(db.scalars(card_statement).unique().all())
    detail = BoardDetail.model_validate(board).model_dump()
    detail["current_user_role"] = get_board_role(db, board.id, actor) or "viewer"
    return BoardSnapshot(
        board=BoardDetail(**detail),
        columns=[ColumnResponse.model_validate(item) for item in columns],
        cards=[CardResponse.model_validate(item) for item in cards],
        server_time=utcnow(),
    )


def get_revision(db: Session, board_id: str, actor: User) -> dict[str, object]:
    board = require_board(db, board_id, allow_archived=True, actor=actor, minimum_role="viewer")
    return {
        "board_id": board.id,
        "revision": board.revision,
        "version": board.version,
        "updated_at": board.updated_at,
    }


def get_activity_page(
    db: Session, board_id: str, limit: int, before_id: int | None, actor: User
) -> tuple[list, int | None]:
    require_board(db, board_id, allow_archived=True, actor=actor, minimum_role="viewer")
    entries = list_activity(db, board_id, limit, before_id)
    return entries, entries[-1].id if len(entries) == limit else None


def list_board_members(db: Session, board_id: str, actor: User) -> list[BoardMemberResponse]:
    require_board(db, board_id, allow_archived=True, actor=actor, minimum_role="viewer")
    rows = db.execute(
        select(BoardMember, User)
        .join(User, User.id == BoardMember.user_id)
        .where(BoardMember.board_id == board_id)
        .order_by(User.display_name, User.username)
    ).all()
    return [
        BoardMemberResponse(
            board_id=member.board_id,
            user_id=member.user_id,
            role=member.role,
            created_at=member.created_at,
            user=UserBrief.model_validate(user),
        )
        for member, user in rows
    ]


def set_board_member(
    db: Session, board_id: str, user_id: str, role: str, actor: User
) -> BoardMemberResponse:
    board = require_board(db, board_id, actor=actor, minimum_role="admin")
    target = require_active_user(db, user_id)
    member = db.scalar(
        select(BoardMember).where(BoardMember.board_id == board_id, BoardMember.user_id == user_id)
    )
    created = member is None
    if member is None:
        member = BoardMember(
            board_id=board_id,
            user_id=user_id,
            role=role,
            created_by_user_id=actor.id,
        )
        db.add(member)
    else:
        member.role = role
    board.revision += 1
    board.version += 1
    board.updated_at = utcnow()
    add_activity(
        db,
        board_id=board_id,
        actor_user_id=actor.id,
        action="board.member_added" if created else "board.member_updated",
        entity_type="user",
        entity_id=user_id,
        summary=f"{target.display_name}: роль на доске — {role}",
    )
    if created:
        add_notification(
            db,
            user_id=user_id,
            type="board_added",
            title="Доступ к доске",
            message=f"Вам предоставлен доступ к доске «{board.title}»",
            actor_user_id=actor.id,
            board_id=board_id,
        )
    db.commit()
    db.refresh(member)
    return BoardMemberResponse(
        board_id=member.board_id,
        user_id=member.user_id,
        role=member.role,
        created_at=member.created_at,
        user=UserBrief.model_validate(target),
    )


def remove_board_member(db: Session, board_id: str, user_id: str, actor: User) -> None:
    board = require_board(db, board_id, actor=actor, minimum_role="admin")
    member = db.scalar(
        select(BoardMember).where(BoardMember.board_id == board_id, BoardMember.user_id == user_id)
    )
    if member is None:
        raise AppError(404, "BOARD_MEMBER_NOT_FOUND", "Участник доски не найден")
    if user_id == actor.id and not is_system_admin(actor):
        raise AppError(400, "SELF_REMOVE_FORBIDDEN", "Администратор доски не может удалить себя")
    db.delete(member)
    board.revision += 1
    board.version += 1
    board.updated_at = utcnow()
    add_activity(
        db,
        board_id=board_id,
        actor_user_id=actor.id,
        action="board.member_removed",
        entity_type="user",
        entity_id=user_id,
        summary="Участник удалён с доски",
    )
    db.commit()
