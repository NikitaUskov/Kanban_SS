"""SQLAlchemy models for users, boards, cards and audit records."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.dbtypes import UTCDateTime
from app.timeutils import new_uuid, utcnow


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utcnow, onupdate=utcnow, nullable=False
    )


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    username: Mapped[str] = mapped_column(String(80), nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(UTCDateTime())

    __table_args__ = (
        UniqueConstraint("username"),
        Index("ix_users_username", "username"),
    )

    refresh_tokens: Mapped[list[RefreshToken]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, nullable=False)

    user: Mapped[User] = relationship(back_populates="refresh_tokens")

    __table_args__ = (Index("ix_refresh_tokens_user_expires", "user_id", "expires_at"),)


class Board(Base, TimestampMixin):
    __tablename__ = "boards"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    created_by_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False
    )
    revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    archived_at: Mapped[datetime | None] = mapped_column(UTCDateTime())

    creator: Mapped[User] = relationship(foreign_keys=[created_by_user_id])
    columns: Mapped[list[Column]] = relationship(
        back_populates="board", cascade="all, delete-orphan", order_by="Column.position"
    )
    cards: Mapped[list[Card]] = relationship(back_populates="board", cascade="all, delete-orphan")


class Column(Base, TimestampMixin):
    __tablename__ = "columns"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    board_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("boards.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(80), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    wip_limit: Mapped[int | None] = mapped_column(Integer)
    is_done: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    archived_at: Mapped[datetime | None] = mapped_column(UTCDateTime())

    board: Mapped[Board] = relationship(back_populates="columns")
    cards: Mapped[list[Card]] = relationship(back_populates="column")

    __table_args__ = (
        CheckConstraint("wip_limit IS NULL OR (wip_limit >= 1 AND wip_limit <= 999)"),
        Index("ix_columns_board_archive_position", "board_id", "archived_at", "position"),
    )


class Card(Base, TimestampMixin):
    __tablename__ = "cards"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    board_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("boards.id", ondelete="CASCADE"), nullable=False
    )
    column_id: Mapped[str] = mapped_column(String(36), ForeignKey("columns.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    priority: Mapped[str] = mapped_column(String(20), default="normal", nullable=False)
    due_date: Mapped[datetime | None] = mapped_column(UTCDateTime())
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_by_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False
    )
    updated_by_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False
    )
    archived_at: Mapped[datetime | None] = mapped_column(UTCDateTime())

    board: Mapped[Board] = relationship(back_populates="cards")
    column: Mapped[Column] = relationship(back_populates="cards")
    created_by: Mapped[User] = relationship(foreign_keys=[created_by_user_id])
    updated_by: Mapped[User] = relationship(foreign_keys=[updated_by_user_id])

    __table_args__ = (
        CheckConstraint("priority IN ('low', 'normal', 'high', 'critical')"),
        Index(
            "ix_cards_board_column_archive_position",
            "board_id",
            "column_id",
            "archived_at",
            "position",
        ),
        Index("ix_cards_due_date", "due_date"),
        Index("ix_cards_priority", "priority"),
    )


class ActivityLog(Base):
    __tablename__ = "activity_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    board_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("boards.id"))
    actor_user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(40), nullable=False)
    entity_id: Mapped[str | None] = mapped_column(String(36))
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    details_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    client_request_id: Mapped[str | None] = mapped_column(String(36), unique=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, nullable=False)

    actor: Mapped[User] = relationship()

    __table_args__ = (Index("ix_activity_board_id_desc", "board_id", "id"),)
