"""SQLAlchemy models for users, access control, boards and collaboration."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, CheckConstraint, ForeignKey, Index, Integer, String, Text
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
    username: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str | None] = mapped_column(String(320))
    email_normalized: Mapped[str | None] = mapped_column(String(320))
    email_verified_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    role: Mapped[str] = mapped_column(String(20), default="member", nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    last_seen_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    notification_settings: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict, nullable=False
    )

    refresh_tokens: Mapped[list[RefreshToken]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    board_memberships: Mapped[list[BoardMember]] = relationship(
        back_populates="user", cascade="all, delete-orphan", foreign_keys="BoardMember.user_id"
    )
    notifications: Mapped[list[Notification]] = relationship(
        back_populates="user", foreign_keys="Notification.user_id", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint("role IN ('owner', 'admin', 'member')"),
        Index("ix_users_username", "username"),
        Index("ix_users_email_normalized", "email_normalized", unique=True),
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


class UserInvitation(Base, TimestampMixin):
    __tablename__ = "user_invitations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    email_normalized: Mapped[str] = mapped_column(String(320), nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    system_role: Mapped[str] = mapped_column(String(20), default="member", nullable=False)
    board_access_json: Mapped[list[dict[str, str]]] = mapped_column(
        JSON, default=list, nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    created_by_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    email_sent_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    email_status: Mapped[str] = mapped_column(String(20), default="created", nullable=False)
    email_error: Mapped[str | None] = mapped_column(Text)

    creator: Mapped[User] = relationship(foreign_keys=[created_by_user_id])

    __table_args__ = (
        CheckConstraint("system_role IN ('admin', 'member')"),
        CheckConstraint("email_status IN ('created', 'sent', 'failed', 'disabled')"),
        Index("ix_user_invitations_email_status", "email_normalized", "accepted_at", "revoked_at"),
        Index("ix_user_invitations_expires_at", "expires_at"),
    )


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, nullable=False)

    user: Mapped[User] = relationship()
    __table_args__ = (Index("ix_password_reset_user_expires", "user_id", "expires_at"),)


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
    members: Mapped[list[BoardMember]] = relationship(
        back_populates="board", cascade="all, delete-orphan"
    )


class BoardMember(Base):
    __tablename__ = "board_members"

    board_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("boards.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    role: Mapped[str] = mapped_column(String(20), default="editor", nullable=False)
    created_by_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, nullable=False)

    board: Mapped[Board] = relationship(back_populates="members")
    user: Mapped[User] = relationship(back_populates="board_memberships", foreign_keys=[user_id])
    created_by: Mapped[User] = relationship(foreign_keys=[created_by_user_id])

    __table_args__ = (
        CheckConstraint("role IN ('admin', 'editor', 'viewer')"),
        Index("ix_board_members_user", "user_id", "board_id"),
    )


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
    parent_card_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("cards.id", ondelete="SET NULL")
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    priority: Mapped[str] = mapped_column(String(20), default="normal", nullable=False)
    due_date: Mapped[datetime | None] = mapped_column(UTCDateTime())
    assignee_user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"))
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
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
    parent: Mapped[Card | None] = relationship(
        remote_side="Card.id", back_populates="subtasks", foreign_keys=[parent_card_id]
    )
    subtasks: Mapped[list[Card]] = relationship(
        back_populates="parent", foreign_keys=[parent_card_id]
    )
    created_by: Mapped[User] = relationship(foreign_keys=[created_by_user_id])
    updated_by: Mapped[User] = relationship(foreign_keys=[updated_by_user_id])
    assignee: Mapped[User | None] = relationship(foreign_keys=[assignee_user_id])
    comments: Mapped[list[CardComment]] = relationship(
        back_populates="card", cascade="all, delete-orphan", order_by="CardComment.created_at"
    )
    checklist_items: Mapped[list[CardChecklistItem]] = relationship(
        back_populates="card", cascade="all, delete-orphan", order_by="CardChecklistItem.position"
    )

    @property
    def comment_count(self) -> int:
        return sum(item.deleted_at is None for item in self.comments)

    @property
    def checklist_total(self) -> int:
        return len(self.checklist_items)

    @property
    def checklist_completed(self) -> int:
        return sum(item.is_completed for item in self.checklist_items)

    @property
    def subtask_total(self) -> int:
        return sum(item.archived_at is None for item in self.subtasks)

    @property
    def subtask_completed(self) -> int:
        return sum(
            item.archived_at is None and item.completed_at is not None for item in self.subtasks
        )

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
        Index("ix_cards_assignee_user_id", "assignee_user_id"),
        Index("ix_cards_completed_at", "completed_at"),
        Index("ix_cards_parent_card_id", "parent_card_id"),
    )


class CardComment(Base, TimestampMixin):
    __tablename__ = "card_comments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    card_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("cards.id", ondelete="CASCADE"), nullable=False
    )
    author_user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    edited_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    deleted_at: Mapped[datetime | None] = mapped_column(UTCDateTime())

    card: Mapped[Card] = relationship(back_populates="comments")
    author: Mapped[User] = relationship(foreign_keys=[author_user_id])

    __table_args__ = (
        Index("ix_card_comments_card_deleted_created", "card_id", "deleted_at", "created_at"),
    )


class CardChecklistItem(Base, TimestampMixin):
    __tablename__ = "card_checklist_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    card_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("cards.id", ondelete="CASCADE"), nullable=False
    )
    text: Mapped[str] = mapped_column(String(500), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    is_completed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    completed_by_user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"))
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    card: Mapped[Card] = relationship(back_populates="checklist_items")
    completed_by: Mapped[User | None] = relationship(foreign_keys=[completed_by_user_id])

    __table_args__ = (Index("ix_card_checklist_card_position", "card_id", "position"),)


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    type: Mapped[str] = mapped_column(String(40), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    board_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("boards.id", ondelete="CASCADE")
    )
    card_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("cards.id", ondelete="CASCADE")
    )
    actor_user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"))
    read_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, nullable=False)

    user: Mapped[User] = relationship(back_populates="notifications", foreign_keys=[user_id])
    actor: Mapped[User | None] = relationship(foreign_keys=[actor_user_id])

    __table_args__ = (
        Index("ix_notifications_user_read_created", "user_id", "read_at", "created_at"),
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
