"""Card request and response schemas."""

from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas import ORMModel
from app.validation import clean_optional_text, clean_single_line

Priority = Literal["low", "normal", "high", "critical"]


class UserBrief(ORMModel):
    id: str
    username: str
    display_name: str


class CardResponse(ORMModel):
    id: str
    board_id: str
    column_id: str
    title: str
    description: str | None
    priority: Priority
    due_date: datetime | None
    position: int
    version: int
    created_by_user_id: str
    updated_by_user_id: str
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None
    created_by: UserBrief
    updated_by: UserBrief


class CardCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    column_id: UUID
    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=20_000)
    priority: Priority = "normal"
    due_date: datetime | None = None
    target_index: int | None = Field(default=None, ge=0)
    client_request_id: UUID | None = None

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str) -> str:
        cleaned = clean_single_line(value)
        if not cleaned:
            raise ValueError("Название карточки не может быть пустым")
        return cleaned

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str | None) -> str | None:
        return clean_optional_text(value)

    @field_validator("due_date")
    @classmethod
    def normalize_due_date(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("due_date должен содержать часовой пояс")
        return value.astimezone(UTC)


class CardUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=20_000)
    clear_description: bool = False
    priority: Priority | None = None
    due_date: datetime | None = None
    clear_due_date: bool = False
    expected_version: int = Field(ge=1)
    client_request_id: UUID | None = None

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = clean_single_line(value)
        if not cleaned:
            raise ValueError("Название карточки не может быть пустым")
        return cleaned

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str | None) -> str | None:
        return clean_optional_text(value)

    @field_validator("due_date")
    @classmethod
    def normalize_due_date(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("due_date должен содержать часовой пояс")
        return value.astimezone(UTC)


class VersionedMutation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    client_request_id: UUID | None = None


class CardMove(VersionedMutation):
    target_column_id: UUID
    target_index: int = Field(ge=0)


class CardRestore(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_column_id: UUID | None = None
    target_index: int | None = Field(default=None, ge=0)
    expected_version: int = Field(ge=1)
    client_request_id: UUID | None = None
