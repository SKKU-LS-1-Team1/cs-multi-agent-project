"""문의 담당 상담원 (CSA-53): tickets.assignee + 담당자별 열린 건수 인덱스 + 배정 이력 assignments

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-21 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 값은 data/ref/agents.csv 의 agent_id. 명단이 없거나 아직 배정 전이면 NULL (부서 큐)
    op.add_column("tickets", sa.Column("assignee", sa.String(length=64), nullable=True))
    op.create_index("ix_tickets_assignee_status", "tickets", ["assignee", "status"], unique=False)
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
    op.drop_index("ix_tickets_assignee_status", table_name="tickets")
    op.drop_column("tickets", "assignee")
