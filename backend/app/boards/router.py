"""Board, snapshot, revision and activity API routes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Query, status
from sqlalchemy.orm import Session

from app.activity.schemas import ActivityItem, ActivityPage
from app.auth.dependencies import CurrentUser
from app.boards.schemas import (
    BoardCreate,
    BoardDetail,
    BoardList,
    BoardSnapshot,
    BoardUpdate,
    BoardVersionMutation,
)
from app.boards.service import (
    archive_board,
    create_board,
    get_activity_page,
    get_board,
    get_revision,
    get_snapshot,
    list_boards,
    restore_board,
    update_board,
)
from app.database import get_db
from app.schemas import RevisionResponse

router = APIRouter(prefix="/boards", tags=["Доски"])
DbSession = Annotated[Session, Depends(get_db)]


@router.get("", response_model=BoardList)
def list_boards_route(
    db: DbSession,
    _user: CurrentUser,
    archived: bool = Query(default=False),
) -> BoardList:
    return list_boards(db, archived)


@router.post("", response_model=BoardDetail, status_code=status.HTTP_201_CREATED)
def create_board_route(payload: BoardCreate, db: DbSession, user: CurrentUser) -> BoardDetail:
    return create_board(db, payload, user)


@router.get("/{board_id}", response_model=BoardDetail)
def get_board_route(board_id: UUID, db: DbSession, _user: CurrentUser) -> BoardDetail:
    return get_board(db, str(board_id))


@router.patch("/{board_id}", response_model=BoardDetail)
def update_board_route(
    board_id: UUID, payload: BoardUpdate, db: DbSession, user: CurrentUser
) -> BoardDetail:
    return update_board(db, str(board_id), payload, user)


@router.delete("/{board_id}", response_model=BoardDetail)
def archive_board_route(
    board_id: UUID,
    db: DbSession,
    user: CurrentUser,
    payload: BoardVersionMutation = Body(...),
) -> BoardDetail:
    return archive_board(db, str(board_id), payload, user)


@router.post("/{board_id}/restore", response_model=BoardDetail)
def restore_board_route(
    board_id: UUID, payload: BoardVersionMutation, db: DbSession, user: CurrentUser
) -> BoardDetail:
    return restore_board(db, str(board_id), payload, user)


@router.get("/{board_id}/snapshot", response_model=BoardSnapshot)
def snapshot_route(
    board_id: UUID,
    db: DbSession,
    _user: CurrentUser,
    include_archived: bool = Query(default=False),
) -> BoardSnapshot:
    return get_snapshot(db, str(board_id), include_archived)


@router.get("/{board_id}/revision", response_model=RevisionResponse)
def revision_route(board_id: UUID, db: DbSession, _user: CurrentUser) -> RevisionResponse:
    return RevisionResponse.model_validate(get_revision(db, str(board_id)))


@router.get("/{board_id}/activity", response_model=ActivityPage)
def activity_route(
    board_id: UUID,
    db: DbSession,
    _user: CurrentUser,
    limit: int = Query(default=50, ge=1, le=200),
    before_id: int | None = Query(default=None, ge=1),
) -> ActivityPage:
    entries, next_id = get_activity_page(db, str(board_id), limit, before_id)
    return ActivityPage(
        items=[ActivityItem.model_validate(item) for item in entries],
        next_before_id=next_id,
    )

