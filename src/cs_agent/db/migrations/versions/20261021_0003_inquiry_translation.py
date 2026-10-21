"""상담원용 고객 문의 한국어 번역 (CSA-57).

Revision ID: 0003
Revises: 0002
"""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tickets", sa.Column("body_ko", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("tickets", "body_ko")
