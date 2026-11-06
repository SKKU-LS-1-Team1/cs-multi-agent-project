"""Customer history search projection and optional follow-up relationship."""

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import JSONB

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("tickets", sa.Column("followup_link", JSONB(), nullable=True))
    op.create_index("ix_tickets_customer_received", "tickets", ["customer_id", "received_at"])
    op.create_table(
        "inquiry_history_chunks",
        sa.Column(
            "ticket_id",
            sa.String(32),
            sa.ForeignKey("tickets.ticket_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("source_id", sa.String(160), primary_key=True),
        sa.Column("customer_id", sa.String(64), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("text_hash", sa.String(64), nullable=False),
        sa.Column("embedding", Vector(1536), nullable=False),
        sa.Column("embedding_version", sa.String(160), nullable=False),
        sa.Column("indexed_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_history_customer_ticket", "inquiry_history_chunks", ["customer_id", "ticket_id"]
    )


def downgrade():
    op.drop_table("inquiry_history_chunks")
    op.drop_index("ix_tickets_customer_received", table_name="tickets")
    op.drop_column("tickets", "followup_link")
