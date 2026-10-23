# PostgreSQL 스키마 (CSA-24 · 담당 김동규 · Sprint 1)
#
# SQLAlchemy 2.0 선언형(Mapped, mapped_column). 열 이름은 schemas.py 필드와 맞춘다.
# 테이블을 바꾸면 Alembic 리비전을 추가한다 (db/migrations, 사용법은 db/session.py).
# 그래프 체크포인트 테이블은 langgraph-checkpoint-postgres 가 따로 만든다.
#
# | 테이블 | 한 행 | 쓰는 곳 |
# |---|---|---|
# | tickets | 문의 1건 + 분석·규칙 결과 + 상태·SLA | 작업 목록·대시보드 (CSA-20·40·43) |
# | drafts | 추천 답변·추가정보 요청문 한 버전 (재작성마다 새 행) | 검토 화면 (CSA-41·42) |
# | reviews | 상담원 버튼 한 번 (승인·수정·재작성·이관·반려) | 피드백 루프, KPI (CSA-50) |
# | assignments | 담당자 배정·재배정 한 번 (누가 → 누구, 사유) | 배정 이력 (CSA-53·54) |
# | chat_sessions · chat_messages | 챗봇 대화 (문의로 전환되면 ticket_id 연결) | CSA-32·45 |
# | resolution_cases | 해결 사례 원본 + 벡터 | 사례 검색 (CSA-15·28) |
# | doc_chunks | 공식 문서·FAQ·정책의 절 단위 조각 + 벡터 | 문서 검색 (CSA-18·28) |
#
# - 상태·유형·행동 값은 domain.py Enum 의 값을 문자열로 저장한다 (DB enum 타입을 쓰지 않아
#   값이 늘어도 마이그레이션이 필요 없다).
# - 목록형·구조형 값(missing_info, evidence, checks …)은 JSONB.
# - 벡터 (pgvector, 팀장 확정: ChromaDB 대신): EMBEDDING_DIM = settings.embedding_dim = 1536.
#   HNSW 인덱스는 2000차원까지라 1536. 차원을 바꾸려면 마이그레이션(열·인덱스 재생성 + 재적재)이
#   필요하다. 확장(CREATE EXTENSION vector)은 첫 리비전이 켠다.
from datetime import UTC, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

EMBEDDING_DIM = 1536  # config.Settings.embedding_dim 과 같아야 한다 (tests/test_db.py 가 확인)


def _now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class _Timestamps:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, server_default=func.now()
    )


class Ticket(Base):
    """문의 1건. 그래프 상태(TicketState)를 조회·집계하기 좋은 열로 펼친 것."""

    __tablename__ = "tickets"

    ticket_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    # ① 접수 (InquiryIn)
    channel: Mapped[str] = mapped_column(String(16))
    customer_id: Mapped[str | None] = mapped_column(String(64))
    customer_tier: Mapped[str] = mapped_column(String(16), default="STANDARD")
    country: Mapped[str | None] = mapped_column(String(8))
    language: Mapped[str | None] = mapped_column(String(8))
    subject: Mapped[str] = mapped_column(Text, default="")
    body: Mapped[str] = mapped_column(Text)
    resolution: Mapped[dict | None] = mapped_column(JSONB)
    body_ko: Mapped[str | None] = mapped_column(Text)  # 상담원 표시용 원문 번역 (CSA-57)
    provided_fields: Mapped[dict] = mapped_column(JSONB, default=dict)  # 문의서에서 고객이 채운 값
    thread_ref: Mapped[str | None] = mapped_column(String(128))  # 후속 문의 연결 키
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    # ② 분류 (Classification)
    category: Mapped[str | None] = mapped_column(String(16))
    secondary_category: Mapped[str | None] = mapped_column(String(16))
    category_confidence: Mapped[float | None] = mapped_column(Float)
    category_model: Mapped[str | None] = mapped_column(String(64))
    # ③ 추출 (Extraction)
    product_code: Mapped[str | None] = mapped_column(String(64))
    product_family: Mapped[str | None] = mapped_column(String(32))
    error_code: Mapped[str | None] = mapped_column(String(32))
    fw_version: Mapped[str | None] = mapped_column(String(32))
    serial_no: Mapped[str | None] = mapped_column(String(64))
    urgency_flag: Mapped[str | None] = mapped_column(String(16))
    return_defect: Mapped[bool | None] = mapped_column(Boolean)
    provided_info: Mapped[list] = mapped_column(JSONB, default=list)
    analysis_error: Mapped[str | None] = mapped_column(String(64))  # 분석 대기 사유
    # ⑤ 규칙 (RuleResult) — rule_id 를 같이 남겨 판단 근거를 추적한다 (N-04)
    priority: Mapped[str | None] = mapped_column(String(4))
    priority_rule_id: Mapped[str | None] = mapped_column(String(32))
    assigned_dept: Mapped[str | None] = mapped_column(String(32))
    routing_rule_id: Mapped[str | None] = mapped_column(String(64))
    missing_info: Mapped[list] = mapped_column(JSONB, default=list)
    missing_blocking: Mapped[list] = mapped_column(JSONB, default=list)
    sla_id: Mapped[str | None] = mapped_column(String(32))
    sla_first_response_target_h: Mapped[float | None] = mapped_column(Float)
    sla_resolution_target_h: Mapped[float | None] = mapped_column(Float)
    # ⑥ 이후 상태
    route: Mapped[str | None] = mapped_column(String(16))  # domain.Route
    status: Mapped[str] = mapped_column(String(24), default="NEW")  # domain.TicketStatus
    escalated_to: Mapped[str | None] = mapped_column(String(32))
    assignee: Mapped[str | None] = mapped_column(String(64))  # 담당 상담원 agent_id (CSA-53)
    followups: Mapped[int] = mapped_column(Integer, default=0)  # 재문의 횟수
    customer_wait_hours: Mapped[float] = mapped_column(Float, default=0.0)  # SLA 정지 누적
    waiting_since: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    first_responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, server_default=func.now()
    )

    drafts: Mapped[list["DraftRow"]] = relationship(
        back_populates="ticket", order_by="DraftRow.version"
    )
    reviews: Mapped[list["ReviewRow"]] = relationship(
        back_populates="ticket", order_by="ReviewRow.id"
    )

    __table_args__ = (
        Index("ix_tickets_status_dept", "status", "assigned_dept"),  # 작업 목록·부서 대시보드
        Index("ix_tickets_received_at", "received_at"),
        Index("ix_tickets_thread_ref", "thread_ref"),
        Index("ix_tickets_assignee_status", "assignee", "status"),  # 담당자별 열린 건수 (배정)
    )


class DraftRow(_Timestamps, Base):
    """추천 답변·추가정보 요청문·이관 요청서 한 버전. slots에 요청서 구조도 보존한다."""

    __tablename__ = "drafts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticket_id: Mapped[str] = mapped_column(ForeignKey("tickets.ticket_id", ondelete="CASCADE"))
    version: Mapped[int] = mapped_column(Integer)  # 티켓 안에서 1, 2, 3 …
    kind: Mapped[str] = mapped_column(
        String(16), default="draft"
    )  # draft | info_request | escalation
    text: Mapped[str] = mapped_column(Text)
    template: Mapped[str] = mapped_column(String(64), default="")
    slots: Mapped[dict] = mapped_column(JSONB, default=dict)
    cited: Mapped[list] = mapped_column(JSONB, default=list)  # ["doc_id#section"]
    evidence: Mapped[list] = mapped_column(JSONB, default=list)  # [Evidence]
    checks: Mapped[list] = mapped_column(JSONB, default=list)  # [CheckResult]
    fix_notes: Mapped[list] = mapped_column(JSONB, default=list)  # 이 버전을 쓰게 한 점검 실패 사유
    reviewer_feedback: Mapped[str | None] = mapped_column(Text)  # 이 버전을 쓰게 한 상담원 요청
    model: Mapped[str] = mapped_column(String(64), default="")

    ticket: Mapped[Ticket] = relationship(back_populates="drafts")

    __table_args__ = (UniqueConstraint("ticket_id", "version", name="uq_drafts_ticket_version"),)


class ReviewRow(_Timestamps, Base):
    """상담원 버튼 한 번 (ReviewIn). 그대로 승인 / 원본·수정본·수정 사유 / 반려가 여기서 나온다."""

    __tablename__ = "reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticket_id: Mapped[str] = mapped_column(ForeignKey("tickets.ticket_id", ondelete="CASCADE"))
    draft_id: Mapped[int | None] = mapped_column(ForeignKey("drafts.id", ondelete="SET NULL"))
    acknowledged_failures: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    action: Mapped[str] = mapped_column(String(16))  # domain.ReviewAction
    reviewer: Mapped[str] = mapped_column(String(64), default="")
    edited_text: Mapped[str | None] = mapped_column(Text)
    feedback: Mapped[str | None] = mapped_column(Text)  # 한 줄
    feedback_reason: Mapped[str | None] = mapped_column(String(16))  # domain.FeedbackReason
    escalated_to: Mapped[str | None] = mapped_column(String(32))
    info_items: Mapped[list] = mapped_column(JSONB, default=list)

    ticket: Mapped[Ticket] = relationship(back_populates="reviews")

    __table_args__ = (Index("ix_reviews_ticket_id", "ticket_id"),)


class AssignmentRow(_Timestamps, Base):
    """담당자 배정·재배정 한 번 (services/assignment.py). tickets.assignee 는 마지막 값."""

    __tablename__ = "assignments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticket_id: Mapped[str] = mapped_column(ForeignKey("tickets.ticket_id", ondelete="CASCADE"))
    from_assignee: Mapped[str | None] = mapped_column(String(64))  # 처음 배정이면 NULL
    to_assignee: Mapped[str | None] = mapped_column(String(64))  # 부서 큐로 되돌리면 NULL
    reason: Mapped[str] = mapped_column(Text, default="")  # 자동 배정 / 이관 / 상담원 사유
    assigned_by: Mapped[str] = mapped_column(String(64), default="")  # 비면 시스템(자동)

    __table_args__ = (Index("ix_assignments_ticket_id", "ticket_id"),)


class SpecialistRequestRow(_Timestamps, Base):
    """불변 요청과 확인된 회신 1건. 추가 회신은 새로운 요청으로 기록한다."""

    __tablename__ = "specialist_requests"

    request_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    ticket_id: Mapped[str] = mapped_column(ForeignKey("tickets.ticket_id", ondelete="CASCADE"))
    to_dept: Mapped[str] = mapped_column(String(32))
    text: Mapped[str] = mapped_column(Text)
    requested_by: Mapped[str] = mapped_column(String(100))
    channel: Mapped[str] = mapped_column(String(64), default="")
    attachment_names: Mapped[list] = mapped_column(JSONB, default=list)
    reply_id: Mapped[str | None] = mapped_column(String(36), unique=True)
    reply_text: Mapped[str | None] = mapped_column(Text)
    reply_author: Mapped[str | None] = mapped_column(String(100))
    replied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (Index("ix_specialist_requests_ticket_id", "ticket_id"),)


class ChatSession(_Timestamps, Base):
    """챗봇 대화 한 건. 진행 중엔 Redis(cache/store.py), 문의로 전환되면 여기로 옮긴다."""

    __tablename__ = "chat_sessions"

    session_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    ticket_id: Mapped[str | None] = mapped_column(
        ForeignKey("tickets.ticket_id", ondelete="SET NULL")
    )
    customer_id: Mapped[str | None] = mapped_column(String(64))
    language: Mapped[str | None] = mapped_column(String(8))

    messages: Mapped[list["ChatMessageRow"]] = relationship(
        back_populates="session", order_by="ChatMessageRow.seq"
    )


class ChatMessageRow(_Timestamps, Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("chat_sessions.session_id", ondelete="CASCADE")
    )
    seq: Mapped[int] = mapped_column(Integer)  # 대화 안 순서
    role: Mapped[str] = mapped_column(String(16))  # user | assistant
    content: Mapped[str] = mapped_column(Text)
    navigation: Mapped[dict | None] = mapped_column(JSONB)  # 화면 이동 지시

    session: Mapped[ChatSession] = relationship(back_populates="messages")

    __table_args__ = (UniqueConstraint("session_id", "seq", name="uq_chat_messages_session_seq"),)


class ResolutionCase(_Timestamps, Base):
    """해결 사례. 열은 agents/case_memory.build_case() 결과와 같다.

    ticket_id 는 FK 가 아니다: 학습용 사례(data_split=train)는 원천 데이터의 티켓 번호다.
    """

    __tablename__ = "resolution_cases"

    case_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    ticket_id: Mapped[str | None] = mapped_column(String(32))
    text: Mapped[str] = mapped_column(Text)  # 임베딩한 글
    summary: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str | None] = mapped_column(String(16))
    product_code: Mapped[str | None] = mapped_column(String(64))
    product_family: Mapped[str | None] = mapped_column(String(32))
    error_code: Mapped[str | None] = mapped_column(String(32))
    cause: Mapped[str] = mapped_column(Text, default="")
    action: Mapped[str] = mapped_column(Text, default="")
    final_reply: Mapped[str] = mapped_column(Text, default="")
    cited: Mapped[list] = mapped_column(JSONB, default=list)
    resolved_by_dept: Mapped[str | None] = mapped_column(String(32))
    review_action: Mapped[str | None] = mapped_column(String(16))
    edited: Mapped[bool] = mapped_column(Boolean, default=False)
    feedback: Mapped[str | None] = mapped_column(Text)
    feedback_reason: Mapped[str | None] = mapped_column(String(16))
    source_fix_needed: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)  # 재문의로 다시 열리면 False
    data_split: Mapped[str] = mapped_column(String(8), default="live")  # train | live
    text_hash: Mapped[str | None] = mapped_column(String(64))  # 글이 그대로면 임베딩 생략
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))

    __table_args__ = (
        Index("ix_resolution_cases_category_product", "category", "product_code"),
        Index(
            "ix_resolution_cases_embedding",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )


class DocChunk(_Timestamps, Base):
    """문서 조각 (pipeline/chunking.py → embed_docs.py 가 upsert)."""

    __tablename__ = "doc_chunks"

    id: Mapped[str] = mapped_column(String(160), primary_key=True)  # "doc_id#section"
    doc_id: Mapped[str] = mapped_column(String(96))
    section: Mapped[str | None] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(Text, default="")
    doc_type: Mapped[str | None] = mapped_column(String(32))
    product_code: Mapped[str | None] = mapped_column(String(64))
    family: Mapped[str | None] = mapped_column(String(32))
    revision: Mapped[str | None] = mapped_column(String(32))
    language: Mapped[str | None] = mapped_column(String(8))
    text: Mapped[str] = mapped_column(Text)
    text_hash: Mapped[str | None] = mapped_column(String(64))
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))

    __table_args__ = (
        Index("ix_doc_chunks_doc_id", "doc_id"),
        Index("ix_doc_chunks_family_type", "family", "doc_type"),
        Index(
            "ix_doc_chunks_embedding",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )
