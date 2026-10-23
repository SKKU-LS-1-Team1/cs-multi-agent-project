"""담당자 완료 결과와 최종 점검 실패 승인 기록.

Revision ID: 0006
Revises: 0005
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tickets", sa.Column("resolution", postgresql.JSONB(), nullable=True))
    op.add_column(
        "reviews",
        sa.Column("acknowledged_failures", sa.Boolean(), server_default=sa.false(), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("reviews", "acknowledged_failures")
    op.drop_column("tickets", "resolution")
