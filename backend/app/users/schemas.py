"""Public user directory schemas."""

from pydantic import BaseModel

from app.schemas import ORMModel


class UserPublic(ORMModel):
    id: str
    username: str
    display_name: str
    is_active: bool


class UserPublicList(BaseModel):
    items: list[UserPublic]
