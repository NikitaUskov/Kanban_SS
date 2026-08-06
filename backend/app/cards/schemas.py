"""Card, subtasks, comments and checklist request/response schemas."""

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


class CommentResponse(ORMModel):
    id: str
    card_id: str
    author_user_id: str
    body: str
    version: int
    created_at: datetime
    updated_at: datetime
    edited_at: datetime | None
    deleted_at: datetime | None
    author: UserBrief


class ChecklistItemResponse(ORMModel):
    id: str
    card_id: str
    text: str
    position: int
    is_completed: bool
    completed_by_user_id: str | None
    completed_at: datetime | None
    version: int
    created_at: datetime
    updated_at: datetime
    completed_by: UserBrief | None


class CardResponse(ORMModel):
    id: str
    board_id: str
    column_id: str
    parent_card_id: str | None
    title: str
    description: str | None
    priority: Priority
    due_date: datetime | None
    assignee_user_id: str | None
    completed_at: datetime | None
    position: int
    version: int
    created_by_user_id: str
    updated_by_user_id: str
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None
    created_by: UserBrief
    updated_by: UserBrief
    assignee: UserBrief | None
    comment_count: int
    checklist_total: int
    checklist_completed: int
    subtask_total: int
    subtask_completed: int


class CardDetailResponse(CardResponse):
    comments: list[CommentResponse]
    checklist_items: list[ChecklistItemResponse]
    subtasks: list[CardResponse]


class CardCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    column_id: UUID
    parent_card_id: UUID | None = None
    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=20_000)
    priority: Priority = "normal"
    due_date: datetime | None = None
    assignee_user_id: UUID | None = None
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
    assignee_user_id: UUID | None = None
    clear_assignee: bool = False
    completed: bool | None = None
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


class CommentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    body: str = Field(min_length=1, max_length=10_000)
    client_request_id: UUID | None = None

    @field_validator("body")
    @classmethod
    def normalize_body(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Комментарий не может быть пустым")
        return cleaned


class CommentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    body: str = Field(min_length=1, max_length=10_000)
    expected_version: int = Field(ge=1)
    client_request_id: UUID | None = None

    @field_validator("body")
    @classmethod
    def normalize_body(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Комментарий не может быть пустым")
        return cleaned


class ChecklistItemCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=500)
    target_index: int | None = Field(default=None, ge=0)
    client_request_id: UUID | None = None

    @field_validator("text")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        cleaned = clean_single_line(value)
        if not cleaned:
            raise ValueError("Пункт чек-листа не может быть пустым")
        return cleaned


class ChecklistItemUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str | None = Field(default=None, min_length=1, max_length=500)
    is_completed: bool | None = None
    expected_version: int = Field(ge=1)
    client_request_id: UUID | None = None

    @field_validator("text")
    @classmethod
    def normalize_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = clean_single_line(value)
        if not cleaned:
            raise ValueError("Пункт чек-листа не может быть пустым")
        return cleaned


class ChecklistItemMove(VersionedMutation):
    target_index: int = Field(ge=0)
