import os

import pytest
from sqlalchemy import inspect, select, text

from cs_agent.agents.case_memory import build_case
from cs_agent.config import Settings
from cs_agent.db.models import (
    EMBEDDING_DIM,
    Base,
    ChatMessageRow,
    ChatSession,
    DocChunk,
    DraftRow,
    ResolutionCase,
    ReviewRow,
    Ticket,
)
from cs_agent.domain import Category, ReviewAction, TicketStatus
from cs_agent.schemas import Classification, Draft, Extraction, InquiryIn, ReviewIn, RuleResult

# 실제 PostgreSQL(pgvector) 이 있을 때만 도는 테스트. CI 는 서비스 컨테이너로 켠다.
#   docker run -d -p 55432:5432 -e POSTGRES_USER=cs -e POSTGRES_PASSWORD=cs -e POSTGRES_DB=cs \
#     pgvector/pgvector:0.8.0-pg16
#   TEST_DATABASE_URL=postgresql+psycopg://cs:cs@localhost:55432/cs uv run pytest tests/test_db.py
TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
needs_db = pytest.mark.skipif(not TEST_DATABASE_URL, reason="TEST_DATABASE_URL 없음")


def _include_name(name, type_, parent_names) -> bool:
    checkpoint = {"checkpoints", "checkpoint_blobs", "checkpoint_writes", "checkpoint_migrations"}
    return not (type_ == "table" and name in checkpoint)


def _columns(model) -> set[str]:
    return set(model.__table__.columns.keys())


# --- 모델 ↔ 공통 스키마 (DB 없이) ----------------------------------------------------------


def test_embedding_dim_matches_settings():
    assert Settings(_env_file=None).embedding_dim == EMBEDDING_DIM


def test_rows_keep_every_schema_field():
    """schemas.py 에 필드가 생기면 DB 열도 같이 만들어야 한다."""
    assert set(InquiryIn.model_fields) - {"category", "product_code"} <= _columns(Ticket)
    assert set(Extraction.model_fields) - {"urgency"} <= _columns(Ticket)  # urgency_flag
    assert set(RuleResult.model_fields) - {
        "escalate_to",
        "required_info",
        "sla_first_response_h",
        "sla_resolution_h",
    } <= _columns(Ticket)
    assert set(Draft.model_fields) <= _columns(DraftRow)
    assert set(ReviewIn.model_fields) <= _columns(ReviewRow) | {"escalate_to"}


def test_case_columns_match_build_case():
    state = {
        "ticket_id": "T-1",
        "inquiry": InquiryIn(channel="email", subject="s", body="b"),
        "classification": Classification(category=Category.DEFECT),
        "extraction": Extraction(),
        "draft": Draft(text="reply"),
        "review": ReviewIn(action=ReviewAction.APPROVE),
    }
    assert set(build_case(state)) <= _columns(ResolutionCase)


# --- 실제 DB --------------------------------------------------------------------------------


@pytest.fixture
def db():
    from alembic import command

    from cs_agent.db.session import alembic_config, get_engine, get_sessionmaker

    config = alembic_config(TEST_DATABASE_URL)
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    yield get_engine(TEST_DATABASE_URL), get_sessionmaker(TEST_DATABASE_URL)
    command.downgrade(config, "base")


@needs_db
def test_migration_matches_models(db):
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext

    engine, _ = db
    with engine.connect() as conn:
        # 체크포인트 테이블(PostgresSaver)은 migrations/env.py 와 같이 비교에서 뺀다
        context = MigrationContext.configure(conn, opts={"include_name": _include_name})
        diff = compare_metadata(context, Base.metadata)
        tables = set(inspect(conn).get_table_names())
        has_vector = conn.execute(text("SELECT 1 FROM pg_extension WHERE extname = 'vector'"))

    assert diff == []  # models.py 를 바꾸고 리비전을 안 만들면 여기서 걸린다
    assert {"tickets", "drafts", "reviews", "chat_sessions", "chat_messages"} <= tables
    assert {"resolution_cases", "doc_chunks"} <= tables
    assert has_vector.scalar() == 1


@needs_db
def test_ticket_history_and_vector_search(db):
    _, Session = db
    with Session.begin() as s:
        ticket = Ticket(
            ticket_id="T-1",
            channel="email",
            body="TRF-OIL-1000 dimensions?",
            category="TECH_SPEC",
            status=TicketStatus.READY_FOR_REVIEW,
        )
        ticket.drafts = [
            DraftRow(version=1, text="v1", checks=[{"name": "values", "passed": False}]),
            DraftRow(version=2, text="v2", fix_notes=["정가 누락"]),
        ]
        s.add(ticket)
        s.flush()
        s.add(ReviewRow(ticket_id="T-1", draft_id=ticket.drafts[1].id, action="edit_approve"))
        s.add(ChatSession(session_id="C-1", ticket_id="T-1"))
        s.add(ChatMessageRow(session_id="C-1", seq=1, role="user", content="hi", navigation=None))
        near, far = [1.0] + [0.0] * (EMBEDDING_DIM - 1), [0.0, 1.0] + [0.0] * (EMBEDDING_DIM - 2)
        s.add_all(
            [
                DocChunk(id="D1#1", doc_id="D1", text="near", embedding=near),
                DocChunk(id="D2#1", doc_id="D2", text="far", embedding=far),
            ]
        )

    with Session() as s:
        ticket = s.get(Ticket, "T-1")
        assert [d.version for d in ticket.drafts] == [1, 2]
        assert ticket.drafts[1].fix_notes == ["정가 누락"]
        assert ticket.reviews[0].action == "edit_approve"
        assert ticket.updated_at is not None
        query = [0.9, 0.1] + [0.0] * (EMBEDDING_DIM - 2)
        ranked = s.scalars(
            select(DocChunk.id).order_by(DocChunk.embedding.cosine_distance(query))
        ).all()
        assert ranked == ["D1#1", "D2#1"]


# --- 문의 처리 기록 + 그래프 체크포인트 (services/records.py, graph/builder.py) ----------------


def _db_service(Session, checkpointer):
    from stubs import ANALYSIS

    from cs_agent.graph.builder import GraphDeps, build_ticket_graph
    from cs_agent.llm.router import LLMRouter
    from cs_agent.services.records import SqlRecords
    from cs_agent.services.tickets import TicketService

    deps = GraphDeps(llm=LLMRouter(Settings(_env_file=None)), **ANALYSIS)
    embed = lambda texts: [[1.0] + [0.0] * (EMBEDDING_DIM - 1) for _ in texts]  # noqa: E731
    return TicketService(build_ticket_graph(deps, checkpointer), SqlRecords(Session, embed))


@needs_db
def test_service_records_rows_and_survives_restart(db):
    from cs_agent.graph.builder import postgres_checkpointer

    engine, Session = db
    inquiry = InquiryIn(
        channel="email",
        customer_tier="GOLD",
        subject="Dimensions of TRF-OIL-1000",
        body="What are the dimensions and weight of TRF-OIL-1000?",
        category=Category.TECH_SPEC,
        provided_fields={"application": "substation"},
        thread_ref="mail-7",
    )
    try:
        with postgres_checkpointer(TEST_DATABASE_URL) as saver:
            service = _db_service(Session, saver)
            tid = service.submit(inquiry).ticket_id
            service.act(tid, ReviewIn(action=ReviewAction.REWRITE, feedback="짧게"))

        # 서버를 다시 켠 것처럼 새 체크포인터·서비스로 이어서 처리한다
        with postgres_checkpointer(TEST_DATABASE_URL) as saver:
            service = _db_service(Session, saver)
            assert service.get(tid).status == TicketStatus.READY_FOR_REVIEW
            assert service.work_list()[0]["ticket_id"] == tid
            service.act(tid, ReviewIn(action=ReviewAction.APPROVE, reviewer="kim"))
            assert service.resolve(tid).status == TicketStatus.RESOLVED

            with Session() as s:
                ticket = s.get(Ticket, tid)
                assert (ticket.status, ticket.category, ticket.assigned_dept) == (
                    "RESOLVED",
                    "TECH_SPEC",
                    "TS_TRF",
                )
                assert ticket.first_responded_at and ticket.resolved_at
                assert [d.kind for d in ticket.drafts][0] == "draft"
                assert [r.action for r in ticket.reviews] == ["rewrite", "approve"]
                assert ticket.reviews[0].draft_id == ticket.drafts[0].id
                case = s.get(ResolutionCase, f"CASE-{tid}")
                assert (case.active, case.data_split) == (True, "live")
                assert case.embedding is not None and case.text_hash

            # 같은 메일 스레드의 고객 회신 → 같은 티켓을 다시 연다
            again = service.submit(
                InquiryIn(channel="email", body="It tripped again.", thread_ref="mail-7")
            )
            assert again.ticket_id == tid
            with Session() as s:
                assert s.get(Ticket, tid).followups == 1
                assert s.get(ResolutionCase, f"CASE-{tid}").active is False
    finally:
        with engine.begin() as conn:  # 체크포인트 테이블은 alembic downgrade 가 지우지 않는다
            conn.execute(
                text(
                    "DROP TABLE IF EXISTS checkpoints, checkpoint_blobs, checkpoint_writes, "
                    "checkpoint_migrations"
                )
            )
