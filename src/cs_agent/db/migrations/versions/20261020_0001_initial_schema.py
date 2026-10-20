"""첫 스키마 (CSA-24): 문의·추천 답변·상담원 처리·챗봇 대화·해결 사례·문서 조각

Revision ID: 0001
Revises:
Create Date: 2026-10-20 13:47:22.899355
"""

from collections.abc import Sequence

import pgvector.sqlalchemy
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 벡터 열(doc_chunks·resolution_cases.embedding)보다 먼저 켠다. downgrade 에서는 끄지 않는다
    # (같은 DB 의 다른 것이 쓸 수 있다).
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "doc_chunks",
        sa.Column("id", sa.String(length=160), nullable=False),
        sa.Column("doc_id", sa.String(length=96), nullable=False),
        sa.Column("section", sa.String(length=64), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("doc_type", sa.String(length=32), nullable=True),
        sa.Column("product_code", sa.String(length=64), nullable=True),
        sa.Column("family", sa.String(length=32), nullable=True),
        sa.Column("revision", sa.String(length=32), nullable=True),
        sa.Column("language", sa.String(length=8), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("text_hash", sa.String(length=64), nullable=True),
        sa.Column("embedding", pgvector.sqlalchemy.vector.VECTOR(dim=1536), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_doc_chunks_doc_id", "doc_chunks", ["doc_id"], unique=False)
    op.create_index(
        "ix_doc_chunks_embedding",
        "doc_chunks",
        ["embedding"],
        unique=False,
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )
    op.create_index("ix_doc_chunks_family_type", "doc_chunks", ["family", "doc_type"], unique=False)
    op.create_table(
        "resolution_cases",
        sa.Column("case_id", sa.String(length=64), nullable=False),
        sa.Column("ticket_id", sa.String(length=32), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("category", sa.String(length=16), nullable=True),
        sa.Column("product_code", sa.String(length=64), nullable=True),
        sa.Column("product_family", sa.String(length=32), nullable=True),
        sa.Column("error_code", sa.String(length=32), nullable=True),
        sa.Column("cause", sa.Text(), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("final_reply", sa.Text(), nullable=False),
        sa.Column("cited", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("resolved_by_dept", sa.String(length=32), nullable=True),
        sa.Column("review_action", sa.String(length=16), nullable=True),
        sa.Column("edited", sa.Boolean(), nullable=False),
        sa.Column("feedback", sa.Text(), nullable=True),
        sa.Column("feedback_reason", sa.String(length=16), nullable=True),
        sa.Column("source_fix_needed", sa.Boolean(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("data_split", sa.String(length=8), nullable=False),
        sa.Column("text_hash", sa.String(length=64), nullable=True),
        sa.Column("embedding", pgvector.sqlalchemy.vector.VECTOR(dim=1536), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("case_id"),
    )
    op.create_index(
        "ix_resolution_cases_category_product",
        "resolution_cases",
        ["category", "product_code"],
        unique=False,
    )
    op.create_index(
        "ix_resolution_cases_embedding",
        "resolution_cases",
        ["embedding"],
        unique=False,
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )
    op.create_table(
        "tickets",
        sa.Column("ticket_id", sa.String(length=32), nullable=False),
        sa.Column("channel", sa.String(length=16), nullable=False),
        sa.Column("customer_id", sa.String(length=64), nullable=True),
        sa.Column("customer_tier", sa.String(length=16), nullable=False),
        sa.Column("country", sa.String(length=8), nullable=True),
        sa.Column("language", sa.String(length=8), nullable=True),
        sa.Column("subject", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("provided_fields", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("thread_ref", sa.String(length=128), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("category", sa.String(length=16), nullable=True),
        sa.Column("secondary_category", sa.String(length=16), nullable=True),
        sa.Column("category_confidence", sa.Float(), nullable=True),
        sa.Column("category_model", sa.String(length=64), nullable=True),
        sa.Column("product_code", sa.String(length=64), nullable=True),
        sa.Column("product_family", sa.String(length=32), nullable=True),
        sa.Column("error_code", sa.String(length=32), nullable=True),
        sa.Column("fw_version", sa.String(length=32), nullable=True),
        sa.Column("serial_no", sa.String(length=64), nullable=True),
        sa.Column("urgency_flag", sa.String(length=16), nullable=True),
        sa.Column("return_defect", sa.Boolean(), nullable=True),
        sa.Column("provided_info", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("analysis_error", sa.String(length=64), nullable=True),
        sa.Column("priority", sa.String(length=4), nullable=True),
        sa.Column("priority_rule_id", sa.String(length=32), nullable=True),
        sa.Column("assigned_dept", sa.String(length=32), nullable=True),
        sa.Column("routing_rule_id", sa.String(length=64), nullable=True),
        sa.Column("missing_info", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("missing_blocking", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("sla_id", sa.String(length=32), nullable=True),
        sa.Column("sla_first_response_target_h", sa.Float(), nullable=True),
        sa.Column("sla_resolution_target_h", sa.Float(), nullable=True),
        sa.Column("route", sa.String(length=16), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("escalated_to", sa.String(length=32), nullable=True),
        sa.Column("followups", sa.Integer(), nullable=False),
        sa.Column("customer_wait_hours", sa.Float(), nullable=False),
        sa.Column("waiting_since", sa.DateTime(timezone=True), nullable=True),
        sa.Column("first_responded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("ticket_id"),
    )
    op.create_index("ix_tickets_received_at", "tickets", ["received_at"], unique=False)
    op.create_index("ix_tickets_status_dept", "tickets", ["status", "assigned_dept"], unique=False)
    op.create_index("ix_tickets_thread_ref", "tickets", ["thread_ref"], unique=False)
    op.create_table(
        "chat_sessions",
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("ticket_id", sa.String(length=32), nullable=True),
        sa.Column("customer_id", sa.String(length=64), nullable=True),
        sa.Column("language", sa.String(length=8), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["ticket_id"], ["tickets.ticket_id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("session_id"),
    )
    op.create_table(
        "drafts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ticket_id", sa.String(length=32), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("template", sa.String(length=64), nullable=False),
        sa.Column("slots", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("cited", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("checks", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("fix_notes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("reviewer_feedback", sa.Text(), nullable=True),
        sa.Column("model", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["ticket_id"], ["tickets.ticket_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ticket_id", "version", name="uq_drafts_ticket_version"),
    )
    op.create_table(
        "chat_messages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("navigation", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["session_id"], ["chat_sessions.session_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", "seq", name="uq_chat_messages_session_seq"),
    )
    op.create_table(
        "reviews",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ticket_id", sa.String(length=32), nullable=False),
        sa.Column("draft_id", sa.Integer(), nullable=True),
        sa.Column("action", sa.String(length=16), nullable=False),
        sa.Column("reviewer", sa.String(length=64), nullable=False),
        sa.Column("edited_text", sa.Text(), nullable=True),
        sa.Column("feedback", sa.Text(), nullable=True),
        sa.Column("feedback_reason", sa.String(length=16), nullable=True),
        sa.Column("escalated_to", sa.String(length=32), nullable=True),
        sa.Column("info_items", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["draft_id"], ["drafts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["ticket_id"], ["tickets.ticket_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_reviews_ticket_id", "reviews", ["ticket_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_reviews_ticket_id", table_name="reviews")
    op.drop_table("reviews")
    op.drop_table("chat_messages")
    op.drop_table("drafts")
    op.drop_table("chat_sessions")
    op.drop_index("ix_tickets_thread_ref", table_name="tickets")
    op.drop_index("ix_tickets_status_dept", table_name="tickets")
    op.drop_index("ix_tickets_received_at", table_name="tickets")
    op.drop_table("tickets")
    op.drop_index(
        "ix_resolution_cases_embedding",
        table_name="resolution_cases",
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )
    op.drop_index("ix_resolution_cases_category_product", table_name="resolution_cases")
    op.drop_table("resolution_cases")
    op.drop_index("ix_doc_chunks_family_type", table_name="doc_chunks")
    op.drop_index(
        "ix_doc_chunks_embedding",
        table_name="doc_chunks",
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )
    op.drop_index("ix_doc_chunks_doc_id", table_name="doc_chunks")
    op.drop_table("doc_chunks")
