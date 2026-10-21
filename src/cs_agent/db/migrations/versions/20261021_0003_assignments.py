"""배정 이력 (CSA-53): assignments — 담당자 배정·재배정 한 번 (누가 → 누구, 사유)

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-21 12:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "assignments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ticket_id", sa.String(length=32), nullable=False),
        sa.Column("from_assignee", sa.String(length=64), nullable=True),
        sa.Column("to_assignee", sa.String(length=64), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("assigned_by", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["ticket_id"], ["tickets.ticket_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_assignments_ticket_id", "assignments", ["ticket_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_assignments_ticket_id", table_name="assignments")
    op.drop_table("assignments")
