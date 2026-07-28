"""Board business logic and snapshot queries."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.activity.service import add_activity, find_idempotent, list_activity
from app.boards.schemas import (
    BoardCreate,
    BoardDetail,
    BoardList,
    BoardListItem,
    BoardResponse,
    BoardSnapshot,
    BoardUpdate,
    BoardVersionMutation,
)
from app.cards.schemas import CardResponse
from app.columns.schemas import ColumnResponse
from app.concurrency import write_coordinator
from app.errors import AppError
from app.models import Board, Card, Column, User
from app.timeutils import utcnow

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
) -> Board:
    statement = select(Board).where(Board.id == board_id)
    if load_creator:
        statement = statement.options(joinedload(Board.creator))
    board = db.scalar(statement)
    if board is None:
        raise AppError(404, "BOARD_NOT_FOUND", "Доска не найдена")
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


def _get_board_detail(db: Session, board_id: str) -> Board:
    return require_board(db, board_id, allow_archived=True, load_creator=True)


def list_boards(db: Session, archived: bool) -> BoardList:
    column_count = (
        select(func.count(Column.id))
        .where(Column.board_id == Board.id, Column.archived_at.is_(None))
        .correlate(Board)
        .scalar_subquery()
    )
    card_count = (
        select(func.count(Card.id))
        .where(Card.board_id == Board.id, Card.archived_at.is_(None))
        .correlate(Board)
        .scalar_subquery()
    )
    archive_filter = Board.archived_at.is_not(None) if archived else Board.archived_at.is_(None)
    rows = db.execute(
        select(
            Board,
            column_count.label("column_count"),
            card_count.label("active_card_count"),
        )
        .where(archive_filter)
        .order_by(Board.updated_at.desc(), Board.title.asc())
    ).all()
    return BoardList(
        items=[
            BoardListItem(
                **BoardResponse.model_validate(board).model_dump(),
                column_count=int(columns or 0),
                active_card_count=int(cards or 0),
            )
            for board, columns, cards in rows
        ]
    )


def get_board(db: Session, board_id: str) -> BoardDetail:
    return BoardDetail.model_validate(_get_board_detail(db, board_id))


def create_board(db: Session, payload: BoardCreate, actor: User) -> BoardDetail:
    request_id = str(payload.client_request_id) if payload.client_request_id else None
    with write_coordinator.write():
        try:
            earlier = find_idempotent(db, request_id, "board.created")
            if earlier and earlier.entity_id:
                return BoardDetail.model_validate(_get_board_detail(db, earlier.entity_id))

            board = Board(
                title=payload.title,
                description=payload.description,
                created_by_user_id=actor.id,
            )
            db.add(board)
            db.flush()
            if payload.create_default_columns:
                for position, (title, is_done) in enumerate(DEFAULT_COLUMNS):
                    db.add(
                        Column(
                            board_id=board.id,
                            title=title,
                            position=position,
                            is_done=is_done,
                        )
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
            return BoardDetail.model_validate(_get_board_detail(db, board.id))
        except Exception:
            db.rollback()
            raise


def update_board(db: Session, board_id: str, payload: BoardUpdate, actor: User) -> BoardDetail:
    request_id = str(payload.client_request_id) if payload.client_request_id else None
    with write_coordinator.write():
        try:
            earlier = find_idempotent(db, request_id, "board.updated")
            if earlier and earlier.entity_id:
                return BoardDetail.model_validate(_get_board_detail(db, earlier.entity_id))
            board = require_board(db, board_id)
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
            return BoardDetail.model_validate(_get_board_detail(db, board.id))
        except Exception:
            db.rollback()
            raise


def archive_board(
    db: Session, board_id: str, payload: BoardVersionMutation, actor: User
) -> BoardDetail:
    request_id = str(payload.client_request_id) if payload.client_request_id else None
    with write_coordinator.write():
        try:
            earlier = find_idempotent(db, request_id, "board.archived")
            if earlier and earlier.entity_id:
                return BoardDetail.model_validate(_get_board_detail(db, earlier.entity_id))
            board = require_board(db, board_id)
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
                client_request_id=request_id,
            )
            db.commit()
            return BoardDetail.model_validate(_get_board_detail(db, board.id))
        except Exception:
            db.rollback()
            raise


def restore_board(
    db: Session, board_id: str, payload: BoardVersionMutation, actor: User
) -> BoardDetail:
    request_id = str(payload.client_request_id) if payload.client_request_id else None
    with write_coordinator.write():
        try:
            earlier = find_idempotent(db, request_id, "board.restored")
            if earlier and earlier.entity_id:
                return BoardDetail.model_validate(_get_board_detail(db, earlier.entity_id))
            board = require_board(db, board_id, allow_archived=True)
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
                client_request_id=request_id,
            )
            db.commit()
            return BoardDetail.model_validate(_get_board_detail(db, board.id))
        except Exception:
            db.rollback()
            raise


def get_snapshot(db: Session, board_id: str, include_archived: bool) -> BoardSnapshot:
    board = require_board(db, board_id, allow_archived=True, load_creator=True)
    column_statement = (
        select(Column).where(Column.board_id == board_id).order_by(Column.position, Column.id)
    )
    card_statement = (
        select(Card)
        .options(joinedload(Card.created_by), joinedload(Card.updated_by))
        .where(Card.board_id == board_id)
        .order_by(Card.column_id, Card.position, Card.id)
    )
    if not include_archived:
        column_statement = column_statement.where(Column.archived_at.is_(None))
        card_statement = card_statement.where(Card.archived_at.is_(None))
    columns = list(db.scalars(column_statement).all())
    cards = list(db.scalars(card_statement).unique().all())
    return BoardSnapshot(
        board=BoardDetail.model_validate(board),
        columns=[ColumnResponse.model_validate(item) for item in columns],
        cards=[CardResponse.model_validate(item) for item in cards],
        server_time=utcnow(),
    )


def get_revision(db: Session, board_id: str) -> dict[str, object]:
    board = require_board(db, board_id, allow_archived=True)
    return {
        "board_id": board.id,
        "revision": board.revision,
        "version": board.version,
        "updated_at": board.updated_at,
    }


def get_activity_page(
    db: Session, board_id: str, limit: int, before_id: int | None
) -> tuple[list, int | None]:
    require_board(db, board_id, allow_archived=True)
    entries = list_activity(db, board_id, limit, before_id)
    next_id = entries[-1].id if len(entries) == limit else None
    return entries, next_id
