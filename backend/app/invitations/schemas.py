"""Invitation and password-reset schemas."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas import ORMModel
from app.users.schemas import UserPublic, clean_email
from app.validation import clean_single_line

BoardRole = Literal["admin", "editor", "viewer"]
SystemInviteRole = Literal["admin", "member"]


class BoardAccessInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    board_id: UUID
    role: BoardRole = "editor"


class InvitationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=320)
    display_name: str = Field(min_length=1, max_length=120)
    system_role: SystemInviteRole = "member"
    board_access: list[BoardAccessInput] = Field(default_factory=list, max_length=100)
    send_email: bool = True

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        result = clean_email(value)
        if result is None:
            raise ValueError("Email обязателен")
        return result

    @field_validator("display_name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        cleaned = clean_single_line(value)
        if not cleaned:
            raise ValueError("Имя обязательно")
        return cleaned


class InvitationResponse(ORMModel):
    id: str
    email: str
    display_name: str
    system_role: str
    board_access_json: list[dict[str, str]]
    created_by_user_id: str
    expires_at: datetime
    accepted_at: datetime | None
    revoked_at: datetime | None
    email_sent_at: datetime | None
    email_status: str
    email_error: str | None
    created_at: datetime
    updated_at: datetime
    invite_url: str | None = None


class InvitationList(BaseModel):
    items: list[InvitationResponse]


class InvitationPreview(BaseModel):
    email: str
    display_name: str
    expires_at: datetime
    system_role: str


class InvitationAccept(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str = Field(min_length=20, max_length=500)
    username: str = Field(min_length=3, max_length=80)
    display_name: str | None = Field(default=None, max_length=120)
    password: str = Field(min_length=8, max_length=1024)

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("display_name")
    @classmethod
    def normalize_display_name(cls, value: str | None) -> str | None:
        return clean_single_line(value) if value else None


class InvitationAcceptResponse(BaseModel):
    user: UserPublic
    message: str


class PasswordResetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(min_length=3, max_length=320)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return clean_email(value) or ""


class PasswordResetConfirm(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str = Field(min_length=20, max_length=500)
    new_password: str = Field(min_length=8, max_length=1024)


class ManualResetLink(BaseModel):
    reset_url: str
    expires_at: datetime
