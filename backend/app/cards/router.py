"""Card, comments and checklist API routes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Response, status
from sqlalchemy.orm import Session

from app.auth.dependencies import CurrentUser
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
from app.cards.service import (
    add_checklist_item,
    add_comment,
    archive_card,
    create_card,
    delete_checklist_item,
    delete_comment,
    get_card,
    move_card,
    move_checklist_item,
    restore_card,
    update_card,
    update_checklist_item,
    update_comment,
)
from app.database import get_db

router = APIRouter(tags=["Карточки"])
DbSession = Annotated[Session, Depends(get_db)]


@router.post(
    "/boards/{board_id}/cards",
    response_model=CardResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_card_route(
    board_id: UUID, payload: CardCreate, db: DbSession, user: CurrentUser
) -> CardResponse:
    return create_card(db, str(board_id), payload, user)


@router.get("/cards/{card_id}", response_model=CardDetailResponse)
def get_card_route(card_id: UUID, db: DbSession, user: CurrentUser) -> CardDetailResponse:
    return get_card(db, str(card_id), user)


@router.patch("/cards/{card_id}", response_model=CardResponse)
def update_card_route(
    card_id: UUID, payload: CardUpdate, db: DbSession, user: CurrentUser
) -> CardResponse:
    return update_card(db, str(card_id), payload, user)


@router.delete("/cards/{card_id}", response_model=CardResponse)
def archive_card_route(
    card_id: UUID,
    db: DbSession,
    user: CurrentUser,
    payload: VersionedMutation = Body(...),
) -> CardResponse:
    return archive_card(db, str(card_id), payload, user)


@router.post("/cards/{card_id}/restore", response_model=CardResponse)
def restore_card_route(
    card_id: UUID, payload: CardRestore, db: DbSession, user: CurrentUser
) -> CardResponse:
    return restore_card(db, str(card_id), payload, user)


@router.post("/cards/{card_id}/move", response_model=CardResponse)
def move_card_route(
    card_id: UUID, payload: CardMove, db: DbSession, user: CurrentUser
) -> CardResponse:
    return move_card(db, str(card_id), payload, user)


@router.post(
    "/cards/{card_id}/comments",
    response_model=CommentResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_comment_route(
    card_id: UUID, payload: CommentCreate, db: DbSession, user: CurrentUser
) -> CommentResponse:
    return add_comment(db, str(card_id), payload, user)


@router.patch("/comments/{comment_id}", response_model=CommentResponse)
def update_comment_route(
    comment_id: UUID, payload: CommentUpdate, db: DbSession, user: CurrentUser
) -> CommentResponse:
    return update_comment(db, str(comment_id), payload, user)


@router.delete("/comments/{comment_id}", response_model=CommentResponse)
def delete_comment_route(
    comment_id: UUID,
    db: DbSession,
    user: CurrentUser,
    payload: VersionedMutation = Body(...),
) -> CommentResponse:
    return delete_comment(db, str(comment_id), payload, user)


@router.post(
    "/cards/{card_id}/checklist-items",
    response_model=ChecklistItemResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_checklist_item_route(
    card_id: UUID,
    payload: ChecklistItemCreate,
    db: DbSession,
    user: CurrentUser,
) -> ChecklistItemResponse:
    return add_checklist_item(db, str(card_id), payload, user)


@router.patch("/checklist-items/{item_id}", response_model=ChecklistItemResponse)
def update_checklist_item_route(
    item_id: UUID,
    payload: ChecklistItemUpdate,
    db: DbSession,
    user: CurrentUser,
) -> ChecklistItemResponse:
    return update_checklist_item(db, str(item_id), payload, user)


@router.post("/checklist-items/{item_id}/move", response_model=ChecklistItemResponse)
def move_checklist_item_route(
    item_id: UUID,
    payload: ChecklistItemMove,
    db: DbSession,
    user: CurrentUser,
) -> ChecklistItemResponse:
    return move_checklist_item(db, str(item_id), payload, user)


@router.delete("/checklist-items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_checklist_item_route(
    item_id: UUID,
    db: DbSession,
    user: CurrentUser,
    payload: VersionedMutation = Body(...),
) -> Response:
    delete_checklist_item(db, str(item_id), payload, user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
