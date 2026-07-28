"""Health endpoint response schemas."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class HealthResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    status: str
    app_version: str = Field(alias="appVersion")
    api_version: str = Field(alias="apiVersion")
    database: str
    time: datetime


class ReadyResponse(HealthResponse):
    alembic_revision: str = Field(alias="alembicRevision")
    required_tables: list[str] = Field(alias="requiredTables")
