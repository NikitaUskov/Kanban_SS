"""Card API routes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Depends, status
from sqlalchemy.orm import Session

from app.auth.dependencies import CurrentUser
from app.cards.schemas import (
    CardCreate,
    CardMove,
    CardResponse,
    CardRestore,
    CardUpdate,
    VersionedMutation,
)
from app.cards.service import (
    archive_card,
    create_card,
    get_card,
    move_card,
    restore_card,
    update_card,
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


@router.get("/cards/{card_id}", response_model=CardResponse)
def get_card_route(card_id: UUID, db: DbSession, _user: CurrentUser) -> CardResponse:
    return get_card(db, str(card_id))


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

