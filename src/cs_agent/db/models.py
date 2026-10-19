"""PostgreSQL 스키마 (CSA-24 · 담당 조수빈): 문의 · 추천 답변 · 수정 기록 · 대화 기록 · 해결 사례.

TODO(CSA-24): Alembic 마이그레이션 추가. 그래프 체크포인트 테이블은 langgraph가 따로 만든다.
"""

from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Ticket(Base):
    __tablename__ = "tickets"

    ticket_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    channel: Mapped[str] = mapped_column(String(20))
    customer_id: Mapped[str | None] = mapped_column(String(32))
    customer_tier: Mapped[str] = mapped_column(String(12))
    language: Mapped[str] = mapped_column(String(8))
    subject: Mapped[str] = mapped_column(Text, default="")
    body: Mapped[str] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(String(20))
    category_confidence: Mapped[float | None] = mapped_column(Float)
    product_code: Mapped[str | None] = mapped_column(String(32))
    error_code: Mapped[str | None] = mapped_column(String(32))
    urgency_flag: Mapped[str] = mapped_column(String(16), default="NONE")
    priority: Mapped[str | None] = mapped_column(String(4))
    priority_rule_id: Mapped[str | None] = mapped_column(String(16))
    assigned_dept: Mapped[str | None] = mapped_column(String(20))
    routing_rule_id: Mapped[str | None] = mapped_column(String(48))
    escalated_to: Mapped[str | None] = mapped_column(String(20))
    missing_info: Mapped[list | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), default="NEW")
    followups: Mapped[int] = mapped_column(Integer, default=0)
    customer_wait_hours: Mapped[float] = mapped_column(Float, default=0)
    sla_first_response_target_h: Mapped[float | None] = mapped_column(Float)
    sla_resolution_target_h: Mapped[float | None] = mapped_column(Float)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    drafts: Mapped[list["DraftRecord"]] = relationship(back_populates="ticket")


class DraftRecord(Base):
    """추천 답변 (재작성 포함 매 버전) + 자동 점검 결과 + 근거."""

    __tablename__ = "drafts"

    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[str] = mapped_column(ForeignKey("tickets.ticket_id"))
    version: Mapped[int] = mapped_column(Integer, default=1)
    kind: Mapped[str] = mapped_column(String(16))  # draft | info_request
    text: Mapped[str] = mapped_column(Text)
    template: Mapped[str | None] = mapped_column(String(32))
    evidence: Mapped[list | None] = mapped_column(JSON)
    checks: Mapped[list | None] = mapped_column(JSON)
    model: Mapped[str | None] = mapped_column(String(48))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    ticket: Mapped[Ticket] = relationship(back_populates="drafts")


class ReviewRecord(Base):
    """상담원 처리 기록: 승인 시각 / 원본·수정본·수정 사유 / 반려 사유 (기획서 6장)."""

    __tablename__ = "reviews"

    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[str] = mapped_column(ForeignKey("tickets.ticket_id"))
    draft_id: Mapped[int | None] = mapped_column(ForeignKey("drafts.id"))
    action: Mapped[str] = mapped_column(String(16))
    reviewer: Mapped[str | None] = mapped_column(String(48))
    edited_text: Mapped[str | None] = mapped_column(Text)
    feedback: Mapped[str | None] = mapped_column(Text)
    feedback_reason: Mapped[str | None] = mapped_column(String(20))
    escalated_to: Mapped[str | None] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    session_id: Mapped[str] = mapped_column(String(48), primary_key=True)
    customer_id: Mapped[str | None] = mapped_column(String(32))
    ticket_id: Mapped[str | None] = mapped_column(ForeignKey("tickets.ticket_id"))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("chat_sessions.session_id"))
    role: Mapped[str] = mapped_column(String(12))  # user | assistant
    text: Mapped[str] = mapped_column(Text)
    navigation: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ResolutionCase(Base):
    """해결 사례 원본 (ChromaDB `cases`에 넣기 전 원본, 기획서 7.1)."""

    __tablename__ = "resolution_cases"

    case_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    ticket_id: Mapped[str | None] = mapped_column(ForeignKey("tickets.ticket_id"))
    category: Mapped[str] = mapped_column(String(20))
    product_code: Mapped[str | None] = mapped_column(String(32))
    error_code: Mapped[str | None] = mapped_column(String(32))
    summary: Mapped[str] = mapped_column(Text)
    cause: Mapped[str | None] = mapped_column(Text)
    action_taken: Mapped[str | None] = mapped_column(Text)
    final_reply: Mapped[str] = mapped_column(Text)
    reference_doc_id: Mapped[str | None] = mapped_column(String(48))
    feedback_reason: Mapped[str | None] = mapped_column(String(20))
    data_split: Mapped[str] = mapped_column(String(8), default="live")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
