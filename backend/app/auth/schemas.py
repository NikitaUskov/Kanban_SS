"""Authentication request and response schemas."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas import ORMModel


def _clean_required(value: str) -> str:
    cleaned = " ".join(value.strip().split())
    if not cleaned:
        raise ValueError("Поле не может быть пустым")
    return cleaned


class UserPublic(ORMModel):
    id: str
    username: str
    display_name: str
    is_active: bool
    last_login_at: datetime | None
    created_at: datetime
    updated_at: datetime


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=1024)

    @field_validator("username")
    @classmethod
    def clean_username(cls, value: str) -> str:
        return _clean_required(value).lower()


class RefreshRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    refresh_token: str = Field(min_length=20, max_length=4096)


class LogoutRequest(RefreshRequest):
    pass


class ChangePasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_password: str = Field(min_length=1, max_length=1024)
    new_password: str = Field(min_length=8, max_length=1024)


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    refresh_expires_in: int
    user: UserPublic
