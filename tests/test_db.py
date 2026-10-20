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
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
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
