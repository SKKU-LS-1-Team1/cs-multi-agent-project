"""CSA-62: 전문부서 검토 요청과 확인된 회신 영속화.

Revision ID: 0005
Revises: 0004
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "specialist_requests",
        sa.Column("request_id", sa.String(36), primary_key=True),
        sa.Column(
            "ticket_id",
            sa.String(32),
            sa.ForeignKey("tickets.ticket_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("to_dept", sa.String(32), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("requested_by", sa.String(100), nullable=False),
        sa.Column("channel", sa.String(64), nullable=False),
        sa.Column("attachment_names", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("reply_id", sa.String(36), unique=True),
        sa.Column("reply_text", sa.Text()),
        sa.Column("reply_author", sa.String(100)),
        sa.Column("replied_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_specialist_requests_ticket_id", "specialist_requests", ["ticket_id"])


def downgrade() -> None:
    op.drop_index("ix_specialist_requests_ticket_id", table_name="specialist_requests")
    op.drop_table("specialist_requests")
