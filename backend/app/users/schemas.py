"""User directory, profile and administrative schemas."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas import ORMModel
from app.validation import clean_single_line

SystemRole = Literal["owner", "admin", "member"]


def clean_email(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip().lower()
    if not cleaned:
        return None
    if len(cleaned) > 320 or "@" not in cleaned or cleaned.startswith("@") or cleaned.endswith("@"):
        raise ValueError("Некорректный email")
    local, domain = cleaned.rsplit("@", 1)
    if not local or "." not in domain or domain.startswith(".") or domain.endswith("."):
        raise ValueError("Некорректный email")
    return cleaned


class UserPublic(ORMModel):
    id: str
    username: str
    display_name: str
    email: str | None
    email_verified_at: datetime | None
    role: SystemRole
    is_active: bool
    last_login_at: datetime | None
    last_seen_at: datetime | None
    notification_settings: dict
    created_at: datetime
    updated_at: datetime


class UserPublicList(BaseModel):
    items: list[UserPublic]


class ProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    notification_settings: dict[str, bool] | None = None

    @field_validator("display_name")
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = clean_single_line(value)
        if not cleaned:
            raise ValueError("Имя не может быть пустым")
        return cleaned


class AdminUserUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    email: str | None = Field(default=None, max_length=320)
    clear_email: bool = False
    role: SystemRole | None = None
    is_active: bool | None = None

    @field_validator("display_name")
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = clean_single_line(value)
        if not cleaned:
            raise ValueError("Имя не может быть пустым")
        return cleaned

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str | None) -> str | None:
        return clean_email(value)


class AdminUserList(BaseModel):
    items: list[UserPublic]
