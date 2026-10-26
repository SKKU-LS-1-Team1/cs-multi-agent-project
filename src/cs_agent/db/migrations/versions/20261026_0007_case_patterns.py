"""해결 사례 패턴 DB (CSA-28): case_patterns + resolution_cases.pattern_id.

처리된 문의를 문의 글 임베딩으로 찾지 않고 패턴(같은 고장 = 같은 원인·조치)으로 묶어 배운다.
근거와 설계는 agents/case_patterns.py.

Revision ID: 0007
Revises: 0006
"""

import pgvector.sqlalchemy
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "case_patterns",
        sa.Column("pattern_id", sa.String(length=64), nullable=False),
        sa.Column("family", sa.String(length=32), nullable=False),
        sa.Column("error_code", sa.String(length=32), nullable=True),
        sa.Column("applies_to", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("source", sa.String(length=8), nullable=False),
        sa.Column("text_hash", sa.String(length=64), nullable=True),
        sa.Column("embedding", pgvector.sqlalchemy.vector.VECTOR(dim=1536), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("pattern_id"),
    )
    op.create_index("ix_case_patterns_family", "case_patterns", ["family"], unique=False)
    op.add_column("resolution_cases", sa.Column("pattern_id", sa.String(length=64), nullable=True))
    op.create_index(
        "ix_resolution_cases_pattern", "resolution_cases", ["pattern_id", "active"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_resolution_cases_pattern", table_name="resolution_cases")
    op.drop_column("resolution_cases", "pattern_id")
    op.drop_index("ix_case_patterns_family", table_name="case_patterns")
    op.drop_table("case_patterns")
