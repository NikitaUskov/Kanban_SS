"""Add assignees, completion, comments and checklists.

Revision ID: 20260730_0002
Revises: 20260727_0001
Create Date: 2026-07-30 17:30:00
"""

from typing import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260730_0002"
down_revision: str | None = "20260727_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("cards") as batch_op:
        batch_op.add_column(sa.Column("assignee_user_id", sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.create_foreign_key(
            "fk_cards_assignee_user_id_users",
            "users",
            ["assignee_user_id"],
            ["id"],
        )
        batch_op.create_index("ix_cards_assignee_user_id", ["assignee_user_id"], unique=False)
        batch_op.create_index("ix_cards_completed_at", ["completed_at"], unique=False)

    op.create_table(
        "card_comments",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("card_id", sa.String(length=36), nullable=False),
        sa.Column("author_user_id", sa.String(length=36), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("edited_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["author_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["card_id"], ["cards.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_card_comments_card_deleted_created",
        "card_comments",
        ["card_id", "deleted_at", "created_at"],
        unique=False,
    )

    op.create_table(
        "card_checklist_items",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("card_id", sa.String(length=36), nullable=False),
        sa.Column("text", sa.String(length=500), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("is_completed", sa.Boolean(), nullable=False),
        sa.Column("completed_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["card_id"], ["cards.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["completed_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_card_checklist_card_position",
        "card_checklist_items",
        ["card_id", "position"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_card_checklist_card_position", table_name="card_checklist_items")
    op.drop_table("card_checklist_items")
    op.drop_index("ix_card_comments_card_deleted_created", table_name="card_comments")
    op.drop_table("card_comments")

    with op.batch_alter_table("cards") as batch_op:
        batch_op.drop_index("ix_cards_completed_at")
        batch_op.drop_index("ix_cards_assignee_user_id")
        batch_op.drop_constraint("fk_cards_assignee_user_id_users", type_="foreignkey")
        batch_op.drop_column("completed_at")
        batch_op.drop_column("assignee_user_id")
