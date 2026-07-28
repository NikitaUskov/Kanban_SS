"""Column request and response schemas."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas import ORMModel
from app.validation import clean_single_line


class ColumnResponse(ORMModel):
    id: str
    board_id: str
    title: str
    position: int
    wip_limit: int | None
    is_done: bool
    version: int
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None


class ColumnCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=80)
    wip_limit: int | None = Field(default=None, ge=1, le=999)
    is_done: bool = False
    target_index: int | None = Field(default=None, ge=0)
    client_request_id: UUID | None = None

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str) -> str:
        cleaned = clean_single_line(value)
        if not cleaned:
            raise ValueError("Название колонки не может быть пустым")
        return cleaned


class ColumnUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=80)
    wip_limit: int | None = Field(default=None, ge=1, le=999)
    clear_wip_limit: bool = False
    is_done: bool | None = None
    expected_version: int = Field(ge=1)
    client_request_id: UUID | None = None

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = clean_single_line(value)
        if not cleaned:
            raise ValueError("Название колонки не может быть пустым")
        return cleaned


class ColumnDelete(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    card_action: Literal["move", "archive"] | None = None
    target_column_id: UUID | None = None
    client_request_id: UUID | None = None

    @model_validator(mode="after")
    def validate_move_target(self) -> "ColumnDelete":
        if self.card_action == "move" and self.target_column_id is None:
            raise ValueError("Для переноса карточек требуется target_column_id")
        if self.card_action != "move" and self.target_column_id is not None:
            raise ValueError("target_column_id используется только вместе с card_action=move")
        return self


class ColumnOrder(BaseModel):
    model_config = ConfigDict(extra="forbid")

    column_ids: list[UUID] = Field(min_length=1)
    expected_board_version: int = Field(ge=1)
    client_request_id: UUID | None = None

    @field_validator("column_ids")
    @classmethod
    def unique_ids(cls, value: list[UUID]) -> list[UUID]:
        if len(value) != len(set(value)):
            raise ValueError("column_ids не должны повторяться")
        return value


class ColumnOrderResponse(BaseModel):
    board_id: str
    revision: int
    version: int
    columns: list[ColumnResponse]
