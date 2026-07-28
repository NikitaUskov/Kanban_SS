"""Column API routes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Depends, status
from sqlalchemy.orm import Session

from app.auth.dependencies import CurrentUser
from app.columns.schemas import (
    ColumnCreate,
    ColumnDelete,
    ColumnOrder,
    ColumnOrderResponse,
    ColumnResponse,
    ColumnUpdate,
)
from app.columns.service import (
    create_column,
    delete_column,
    reorder_columns,
    update_column,
)
from app.database import get_db

router = APIRouter(tags=["Колонки"])
DbSession = Annotated[Session, Depends(get_db)]


@router.post(
    "/boards/{board_id}/columns",
    response_model=ColumnResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_column_route(
    board_id: UUID, payload: ColumnCreate, db: DbSession, user: CurrentUser
) -> ColumnResponse:
    return create_column(db, str(board_id), payload, user)


@router.patch("/columns/{column_id}", response_model=ColumnResponse)
def update_column_route(
    column_id: UUID, payload: ColumnUpdate, db: DbSession, user: CurrentUser
) -> ColumnResponse:
    return update_column(db, str(column_id), payload, user)


@router.delete("/columns/{column_id}", response_model=ColumnResponse)
def delete_column_route(
    column_id: UUID,
    db: DbSession,
    user: CurrentUser,
    payload: ColumnDelete = Body(...),
) -> ColumnResponse:
    return delete_column(db, str(column_id), payload, user)


@router.put("/boards/{board_id}/columns/order", response_model=ColumnOrderResponse)
def reorder_columns_route(
    board_id: UUID, payload: ColumnOrder, db: DbSession, user: CurrentUser
) -> ColumnOrderResponse:
    return reorder_columns(db, str(board_id), payload, user)

