"""Application configuration loaded from environment variables and .env."""

from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from app import API_VERSION, APP_VERSION


class Settings(BaseSettings):
    """Validated runtime configuration."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=False, extra="ignore"
    )

    app_env: str = "development"
    app_host: str = "127.0.0.1"
    app_port: int = Field(default=8000, ge=1, le=65535)
    app_version: str = APP_VERSION
    api_version: str = API_VERSION
    database_url: str = "sqlite:///./data/kanban.db"
    jwt_secret: str = "development-only-change-me-before-public-use"
    jwt_algorithm: str = "HS256"
    access_token_expire_hours: int = Field(default=12, ge=1, le=168)
    refresh_token_expire_days: int = Field(default=30, ge=1, le=365)
    invitation_expire_hours: int = Field(default=72, ge=1, le=720)
    password_reset_expire_minutes: int = Field(default=30, ge=5, le=1440)
    allowed_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://127.0.0.1:5500", "http://localhost:5500"]
    )
    log_level: str = "INFO"
    log_dir: Path = Path("./logs")
    github_pages_url: str = "http://127.0.0.1:5500/"
    frontend_url: str = "http://127.0.0.1:5500/"
    repository_path: Path = Path(".")
    frontend_repository_path: Path = Path(".")
    runtime_config_path: Path = Path("frontend/runtime-config.json")
    login_attempt_limit: int = Field(default=10, ge=1, le=100)
    login_attempt_window_minutes: int = Field(default=10, ge=1, le=1440)

    email_enabled: bool = False
    smtp_host: str = ""
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_use_tls: bool = True
    smtp_timeout_seconds: int = Field(default=15, ge=3, le=120)
    email_from_address: str = ""
    email_from_name: str = "Kanban Board"

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip().rstrip("/") for item in value.split(",") if item.strip()]
        return value

    @field_validator("frontend_url", "github_pages_url")
    @classmethod
    def normalize_frontend_url(cls, value: str) -> str:
        return value.strip().rstrip("/") + "/"

    @field_validator("log_level")
    @classmethod
    def normalize_log_level(cls, value: str) -> str:
        level = value.upper().strip()
        if level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError("Unsupported LOG_LEVEL")
        return level

    @field_validator("jwt_secret")
    @classmethod
    def validate_production_secret(cls, value: str, info) -> str:
        app_env = (info.data.get("app_env") or "development").lower()
        if app_env == "production":
            placeholders = {
                "",
                "<generate-locally>",
                "development-only-change-me-before-public-use",
            }
            if value in placeholders or len(value) < 32:
                raise ValueError(
                    "JWT_SECRET must be generated locally and contain at least 32 characters"
                )
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
