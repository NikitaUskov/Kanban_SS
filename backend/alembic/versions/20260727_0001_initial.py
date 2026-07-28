"""Initial Kanban Board schema.

Revision ID: 20260727_0001
Revises:
Create Date: 2026-07-27 12:00:00
"""

from typing import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260727_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("username", sa.String(length=80), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("username"),
    )
    op.create_index("ix_users_username", "users", ["username"], unique=False)

    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index(
        "ix_refresh_tokens_user_expires",
        "refresh_tokens",
        ["user_id", "expires_at"],
        unique=False,
    )

    op.create_table(
        "boards",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "columns",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("board_id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=80), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("wip_limit", sa.Integer(), nullable=True),
        sa.Column("is_done", sa.Boolean(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "wip_limit IS NULL OR (wip_limit >= 1 AND wip_limit <= 999)",
            name="ck_columns_wip_limit",
        ),
        sa.ForeignKeyConstraint(["board_id"], ["boards.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_columns_board_archive_position",
        "columns",
        ["board_id", "archived_at", "position"],
        unique=False,
    )

    op.create_table(
        "cards",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("board_id", sa.String(length=36), nullable=False),
        sa.Column("column_id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("priority", sa.String(length=20), nullable=False),
        sa.Column("due_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=False),
        sa.Column("updated_by_user_id", sa.String(length=36), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "priority IN ('low', 'normal', 'high', 'critical')",
            name="ck_cards_priority",
        ),
        sa.ForeignKeyConstraint(["board_id"], ["boards.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["column_id"], ["columns.id"]),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_cards_board_column_archive_position",
        "cards",
        ["board_id", "column_id", "archived_at", "position"],
        unique=False,
    )
    op.create_index("ix_cards_due_date", "cards", ["due_date"], unique=False)
    op.create_index("ix_cards_priority", "cards", ["priority"], unique=False)

    op.create_table(
        "activity_log",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("board_id", sa.String(length=36), nullable=True),
        sa.Column("actor_user_id", sa.String(length=36), nullable=False),
        sa.Column("action", sa.String(length=80), nullable=False),
        sa.Column("entity_type", sa.String(length=40), nullable=False),
        sa.Column("entity_id", sa.String(length=36), nullable=True),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("details_json", sa.JSON(), nullable=True),
        sa.Column("client_request_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["board_id"], ["boards.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("client_request_id"),
    )
    op.create_index(
        "ix_activity_board_id_desc",
        "activity_log",
        ["board_id", "id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_activity_board_id_desc", table_name="activity_log")
    op.drop_table("activity_log")
    op.drop_index("ix_cards_priority", table_name="cards")
    op.drop_index("ix_cards_due_date", table_name="cards")
    op.drop_index("ix_cards_board_column_archive_position", table_name="cards")
    op.drop_table("cards")
    op.drop_index("ix_columns_board_archive_position", table_name="columns")
    op.drop_table("columns")
    op.drop_table("boards")
    op.drop_index("ix_refresh_tokens_user_expires", table_name="refresh_tokens")
    op.drop_table("refresh_tokens")
    op.drop_index("ix_users_username", table_name="users")
    op.drop_table("users")

