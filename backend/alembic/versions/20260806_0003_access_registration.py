"""Add invitations, board access, notifications and subtasks.

Revision ID: 20260806_0003
Revises: 20260730_0002
Create Date: 2026-08-06 09:50:00
"""

from typing import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260806_0003"
down_revision: str | None = "20260730_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(sa.Column("email", sa.String(length=320), nullable=True))
        batch_op.add_column(sa.Column("email_normalized", sa.String(length=320), nullable=True))
        batch_op.add_column(sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(
            sa.Column("role", sa.String(length=20), nullable=False, server_default="member")
        )
        batch_op.add_column(sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(
            sa.Column("notification_settings", sa.JSON(), nullable=False, server_default="{}")
        )
        batch_op.create_check_constraint(
            "ck_users_role", "role IN ('owner', 'admin', 'member')"
        )
        batch_op.create_index(
            "ix_users_email_normalized", ["email_normalized"], unique=True
        )

    # Preserve existing installations: the oldest account becomes owner.
    op.execute(
        "UPDATE users SET role = 'owner' WHERE id = "
        "(SELECT id FROM users ORDER BY created_at ASC, id ASC LIMIT 1)"
    )

    op.create_table(
        "user_invitations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("email_normalized", sa.String(length=320), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column("system_role", sa.String(length=20), nullable=False),
        sa.Column("board_access_json", sa.JSON(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("email_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("email_status", sa.String(length=20), nullable=False),
        sa.Column("email_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("system_role IN ('admin', 'member')", name="ck_invitation_system_role"),
        sa.CheckConstraint(
            "email_status IN ('created', 'sent', 'failed', 'disabled')",
            name="ck_invitation_email_status",
        ),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index(
        "ix_user_invitations_email_status",
        "user_invitations",
        ["email_normalized", "accepted_at", "revoked_at"],
        unique=False,
    )
    op.create_index(
        "ix_user_invitations_expires_at",
        "user_invitations",
        ["expires_at"],
        unique=False,
    )

    op.create_table(
        "password_reset_tokens",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index(
        "ix_password_reset_user_expires",
        "password_reset_tokens",
        ["user_id", "expires_at"],
        unique=False,
    )

    op.create_table(
        "board_members",
        sa.Column("board_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("role IN ('admin', 'editor', 'viewer')", name="ck_board_members_role"),
        sa.ForeignKeyConstraint(["board_id"], ["boards.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("board_id", "user_id"),
    )
    op.create_index(
        "ix_board_members_user", "board_members", ["user_id", "board_id"], unique=False
    )

    # Existing users previously saw every board. Keep that behavior after migration.
    op.execute(
        "INSERT INTO board_members (board_id, user_id, role, created_by_user_id, created_at) "
        "SELECT b.id, u.id, CASE WHEN b.created_by_user_id = u.id THEN 'admin' ELSE 'editor' END, "
        "b.created_by_user_id, CURRENT_TIMESTAMP FROM boards b CROSS JOIN users u"
    )

    with op.batch_alter_table("cards") as batch_op:
        batch_op.add_column(sa.Column("parent_card_id", sa.String(length=36), nullable=True))
        batch_op.create_foreign_key(
            "fk_cards_parent_card_id_cards",
            "cards",
            ["parent_card_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index("ix_cards_parent_card_id", ["parent_card_id"], unique=False)

    op.create_table(
        "notifications",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("type", sa.String(length=40), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("board_id", sa.String(length=36), nullable=True),
        sa.Column("card_id", sa.String(length=36), nullable=True),
        sa.Column("actor_user_id", sa.String(length=36), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["board_id"], ["boards.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["card_id"], ["cards.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_notifications_user_read_created",
        "notifications",
        ["user_id", "read_at", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_notifications_user_read_created", table_name="notifications")
    op.drop_table("notifications")

    with op.batch_alter_table("cards") as batch_op:
        batch_op.drop_index("ix_cards_parent_card_id")
        batch_op.drop_constraint("fk_cards_parent_card_id_cards", type_="foreignkey")
        batch_op.drop_column("parent_card_id")

    op.drop_index("ix_board_members_user", table_name="board_members")
    op.drop_table("board_members")
    op.drop_index("ix_password_reset_user_expires", table_name="password_reset_tokens")
    op.drop_table("password_reset_tokens")
    op.drop_index("ix_user_invitations_expires_at", table_name="user_invitations")
    op.drop_index("ix_user_invitations_email_status", table_name="user_invitations")
    op.drop_table("user_invitations")

    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_index("ix_users_email_normalized")
        batch_op.drop_constraint("ck_users_role", type_="check")
        batch_op.drop_column("notification_settings")
        batch_op.drop_column("last_seen_at")
        batch_op.drop_column("role")
        batch_op.drop_column("email_verified_at")
        batch_op.drop_column("email_normalized")
        batch_op.drop_column("email")
