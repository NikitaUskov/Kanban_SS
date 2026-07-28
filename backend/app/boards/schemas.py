"""Board request, list and snapshot schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.cards.schemas import CardResponse, UserBrief
from app.columns.schemas import ColumnResponse
from app.schemas import ORMModel
from app.validation import clean_optional_text, clean_single_line


class BoardCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    create_default_columns: bool = True
    client_request_id: UUID | None = None

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str) -> str:
        cleaned = clean_single_line(value)
        if not cleaned:
            raise ValueError("Название доски не может быть пустым")
        return cleaned

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str | None) -> str | None:
        return clean_optional_text(value)


class BoardUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    clear_description: bool = False
    expected_version: int = Field(ge=1)
    client_request_id: UUID | None = None

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = clean_single_line(value)
        if not cleaned:
            raise ValueError("Название доски не может быть пустым")
        return cleaned

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str | None) -> str | None:
        return clean_optional_text(value)


class BoardVersionMutation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    client_request_id: UUID | None = None


class BoardResponse(ORMModel):
    id: str
    title: str
    description: str | None
    created_by_user_id: str
    revision: int
    version: int
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None


class BoardDetail(BoardResponse):
    creator: UserBrief


class BoardListItem(BoardResponse):
    column_count: int
    active_card_count: int


class BoardList(BaseModel):
    items: list[BoardListItem]


class BoardSnapshot(BaseModel):
    board: BoardDetail
    columns: list[ColumnResponse]
    cards: list[CardResponse]
    server_time: datetime

