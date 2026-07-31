"""Shared Pydantic response helpers."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ORMModel(BaseModel):
    """Base response model that reads SQLAlchemy attributes."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class MutationRequest(BaseModel):
    """Fields shared by idempotent mutation bodies."""

    client_request_id: str | None = None


class RevisionResponse(BaseModel):
    board_id: str
    revision: int
    version: int
    updated_at: datetime


class MessageResponse(BaseModel):
    message: str
