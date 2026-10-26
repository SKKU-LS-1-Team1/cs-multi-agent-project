import os

import pytest
from sqlalchemy import inspect, select, text

from cs_agent.agents.case_memory import build_case
from cs_agent.config import Settings
from cs_agent.db.models import (
    EMBEDDING_DIM,
    Base,
    CasePattern,
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
    """조회용 필드는 열로, 추출 실제 값은 체크포인트·초안 slots로 보존한다."""
    assert set(InquiryIn.model_fields) - {"category", "product_code"} <= _columns(Ticket)
    assert set(Extraction.model_fields) - {
        "urgency",
        "field_values",
        "field_evidence",
        "field_sources",
        "unconfirmed_fields",
        "unconfirmed_evidence",
        "field_candidates",
        "issues",
        "assessed_urgency",
        "safety_review_required",
    } <= _columns(Ticket)
    assert set(RuleResult.model_fields) - {
        "escalate_to",
        "required_info",
        "sla_first_response_h",
        "sla_resolution_h",
    } <= _columns(Ticket)
    assert set(Draft.model_fields) <= _columns(DraftRow)
    assert (
        set(ReviewIn.model_fields)
        - {
            "reply_preview_id",  # 체크포인트에 저장된 변환본 식별자
            "expected_specialist_revision",
            "expected_customer_revision",
            "expected_information_reviewed_at",
        }
    ) <= _columns(ReviewRow) | {"escalate_to"}


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


@needs_db
@pytest.mark.parametrize("action", [ReviewAction.APPROVE, ReviewAction.ESCALATE])
def test_escalation_request_persistence_and_review_kind(db, action):
    """요청서 복원 후에도 승인은 답변, 이관은 요청서 버전을 참조한다."""
    from cs_agent.graph.builder import postgres_checkpointer
    from cs_agent.schemas import EscalationRequest

    _engine, Session = db
    inquiry = InquiryIn(
        channel="email",
        language="en",
        category=Category.TECH_SPEC,
        product_code="TRF-OIL-1000",
        body="Please confirm the dimensions.",
        provided_fields={"application": "substation"},
    )
    request = EscalationRequest(
        to_dept="CERT",
        reason="규격 검토 요청",
        summary="대상 규격 확인 요청입니다.",
        fields={"product_code": "TRF-OIL-1000"},
        cited=[],
        text="사내 검토 요청서",
        model="stub",
    )
    with postgres_checkpointer(TEST_DATABASE_URL) as saver:
        service = _db_service(Session, saver)
        service.escalation_writer = lambda *a, **k: request
        tid = service.submit(inquiry).ticket_id
        service.generate_escalation_request(tid)
        service.generate_escalation_request(tid)  # 동일 문서는 중복 저장하지 않는다
        with Session() as s:
            rows = s.scalars(
                select(DraftRow).where(DraftRow.ticket_id == tid, DraftRow.kind == "escalation")
            ).all()
            assert len(rows) == 1
            assert EscalationRequest.model_validate(rows[0].slots) == request

    with postgres_checkpointer(TEST_DATABASE_URL) as saver:
        service = _db_service(Session, saver)
        assert service.get(tid).escalation_request == request
        assert service._state(tid).next == ("review",)
        result = service.act(tid, ReviewIn(action=action))
        expected = "escalation" if action == ReviewAction.ESCALATE else "draft"
        with Session() as s:
            review = s.scalar(select(ReviewRow).where(ReviewRow.ticket_id == tid))
            assert s.get(DraftRow, review.draft_id).kind == expected
        assert result.status == (
            TicketStatus.ESCALATED if action == ReviewAction.ESCALATE else TicketStatus.APPROVED
        )


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
def test_sql_records_keep_extracted_values_in_existing_draft_slots(db):
    from cs_agent.services.records import SqlRecords

    engine, Session = db
    assert "field_values" not in {c["name"] for c in inspect(engine).get_columns("tickets")}
    records = SqlRecords(Session)
    inquiry = InquiryIn(
        channel="email", body="Quantity corrected", provided_fields={"quantity": "5"}
    )
    records.add_ticket("T-FIELDS", inquiry)
    records.save_state(
        "T-FIELDS",
        {
            "inquiry": inquiry,
            "extraction": Extraction(field_values={"quantity": "10", "incoterms": "FOB"}),
            "draft": Draft(text="Quote for 10 units", slots={"quantity": "10", "incoterms": "FOB"}),
        },
    )
    with Session() as session:
        ticket = session.get(Ticket, "T-FIELDS")
        assert ticket.provided_fields == {"quantity": "5"}
        assert ticket.drafts[0].slots == {"quantity": "10", "incoterms": "FOB"}
    records.save_state(
        "T-FIELDS",
        {
            "inquiry": inquiry,
            "extraction": Extraction(),
            "draft": Draft(text="Quantity needs confirmation", slots={}),
        },
    )
    with Session() as session:
        drafts = session.get(Ticket, "T-FIELDS").drafts
        assert [draft.slots for draft in drafts] == [{"quantity": "10", "incoterms": "FOB"}, {}]


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


def _db_service(Session, checkpointer, **agents):
    from stubs import ANALYSIS

    from cs_agent.graph.builder import GraphDeps, build_ticket_graph
    from cs_agent.llm.router import LLMRouter
    from cs_agent.services.records import SqlRecords
    from cs_agent.services.tickets import TicketService

    def extract(inquiry, tables, **kwargs):
        return ANALYSIS["extract"](inquiry, tables, **kwargs).model_copy(
            update={"field_values": dict(inquiry.provided_fields)}
        )

    deps = GraphDeps(
        llm=LLMRouter(Settings(_env_file=None)), **{**ANALYSIS, "extract": extract, **agents}
    )
    embed = lambda texts: [[1.0] + [0.0] * (EMBEDDING_DIM - 1) for _ in texts]  # noqa: E731
    return TicketService(build_ticket_graph(deps, checkpointer), SqlRecords(Session, embed))


@needs_db
def test_sql_records_keep_assignee_and_history(db):
    from cs_agent.services.records import SqlRecords

    _, Session = db
    records = SqlRecords(Session)
    inquiry = InquiryIn(channel="email", subject="s", body="b")
    records.add_ticket("T-1", inquiry)
    records.add_ticket("T-2", inquiry)

    records.set_assignee("T-1", "AG-1", "자동 배정")
    records.set_assignee("T-1", "AG-2", "SLA 75% 경고", by="lead")
    records.set_assignee("T-2", "AG-2", "자동 배정")
    # 그래프 상태로 tickets 행을 덮어써도 담당자는 그대로다 (assignee 는 상태에 없다)
    records.save_state("T-1", {"inquiry": inquiry, "status": TicketStatus.READY_FOR_REVIEW})
    records.save_state("T-2", {"inquiry": inquiry, "status": TicketStatus.REJECTED})

    assert records.assignee_of("T-1") == "AG-2"
    assert records.open_counts(exclude=frozenset({"REJECTED"})) == {"AG-2": 1}
    assert records.open_counts() == {"AG-2": 2}
    history = records.assignments("T-1")
    assert [(h["from_assignee"], h["to_assignee"], h["assigned_by"]) for h in history] == [
        (None, "AG-1", ""),
        ("AG-1", "AG-2", "lead"),
    ]
    assert history[0]["created_at"] is not None


@needs_db
def test_patterns_saved_without_vector_are_embedded_later(db):
    """해결 사례 = 패턴 학습 (CSA-28). 새 패턴 설명 벡터가 없으면(LLM 꺼짐·임베딩 장애)
    embed_missing_cases 가 채운다. 사례 글 자체는 임베딩하지 않는다."""
    from cs_agent.services.records import SqlRecords

    engine, Session = db

    def case(ticket_id: str, cause: str) -> dict:
        return build_case(
            {
                "ticket_id": ticket_id,
                "inquiry": InquiryIn(channel="email", subject=f"q {ticket_id}", body="b"),
                "classification": Classification(category=Category.DEFECT),
                "extraction": Extraction(product_code="INV-LSLV0075-S100", product_family="DRIVE"),
                "draft": Draft(text="reply", slots={"cause": cause}),
                "review": ReviewIn(action=ReviewAction.APPROVE),
            }
        )

    offline = SqlRecords(Session)  # embed_fn 없음 = 벡터 없이 저장
    offline.save_case(case("T-1", "Acceleration time too short for load inertia"))  # FLT-001
    offline.save_case(case("T-2", "Loose terminal on the braking resistor"))  # 새 원인
    offline.save_case(case("T-3", "Acceleration time too short for load inertia"))  # 같은 패턴
    offline.deactivate_case("T-3")

    assert [c["pattern_id"] for c in offline.live_cases()] == [
        "FLT-001",
        case("T-2", "Loose terminal on the braking resistor")["pattern_id"],
    ]
    assert offline.live_cases()[1]["pattern_id"].startswith("LIVE-DRIVE-")
    assert offline.embed_missing_cases() == 0  # 임베딩 함수가 없으면 아무것도 안 한다

    calls = []

    def flaky(texts):
        calls.append(texts)
        if len(calls) == 2:
            raise TimeoutError("embedding down")
        return [[1.0] + [0.0] * (EMBEDDING_DIM - 1) for _ in texts]

    online = SqlRecords(Session, flaky)
    assert online.embed_missing_cases() == 1  # 두 번째에서 장애 → 멈춤 (다음 주기에 다시)
    assert online.embed_missing_cases() == 1
    assert online.embed_missing_cases() == 0

    with engine.connect() as conn:
        patterns = dict(
            conn.execute(text("SELECT pattern_id, embedding IS NOT NULL FROM case_patterns")).all()
        )
        cases = conn.execute(text("SELECT count(embedding) FROM resolution_cases")).scalar()
    assert len(patterns) == 2 and all(patterns.values())  # 같은 고장 T-1·T-3 은 패턴 하나
    assert cases == 0


@needs_db
@pytest.mark.parametrize("customer_language", ["en", "fr"])
def test_service_records_rows_and_survives_restart(db, customer_language):
    from cs_agent.graph.builder import postgres_checkpointer

    engine, Session = db
    inquiry = InquiryIn(
        channel="email",
        language=customer_language,
        customer_tier="GOLD",
        subject="Dimensions of TRF-OIL-1000",
        body="What are the dimensions and weight of TRF-OIL-1000?",
        category=Category.TECH_SPEC,
        provided_fields={"application": "substation"},
        thread_ref="mail-7",
    )

    def translate(text, source, target, llm):
        assert source == "en" and target == customer_language
        return text if target == "en" else "Réponse validée."

    try:
        with postgres_checkpointer(TEST_DATABASE_URL) as saver:
            service = _db_service(Session, saver, translate_reply=translate)
            tid = service.submit(inquiry).ticket_id
            service.act(tid, ReviewIn(action=ReviewAction.REWRITE, feedback="짧게"))

        # 서버를 다시 켠 것처럼 새 체크포인터·서비스로 이어서 처리한다
        with postgres_checkpointer(TEST_DATABASE_URL) as saver:
            service = _db_service(Session, saver, translate_reply=translate)
            assert service.get(tid).status == TicketStatus.READY_FOR_REVIEW
            restored = service.graph.get_state(service._config(tid)).values
            assert restored["extraction"].field_values == {"application": "substation"}
            assert restored["draft"].slots["draft_language"] == "en"
            assert service.work_list()[0]["ticket_id"] == tid
            approved = service.act(tid, ReviewIn(action=ReviewAction.APPROVE, reviewer="kim"))
            assert approved.approved_reply == restored["draft"].text
            assert approved.final_reply_language == customer_language
            if customer_language == "fr":
                assert approved.final_reply == "Réponse validée."
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
                assert case.final_reply == approved.final_reply
                assert (case.active, case.data_split) == (True, "live")
                # 사례 글은 임베딩하지 않고 패턴으로 배운다 (CSA-28): 패턴 행과 설명 벡터가 생긴다
                assert case.embedding is None and case.pattern_id
                pattern = s.get(CasePattern, case.pattern_id)
                assert pattern is not None and pattern.embedding is not None

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


@needs_db
def test_sql_work_list_pauses_sla_while_waiting_for_customer(db, monkeypatch):
    """DB 가 있으면 작업 목록은 db/sql/work_list.sql, 대기 시간은 SqlRecords 가 남긴다."""
    from datetime import UTC, datetime, timedelta

    from cs_agent.graph.builder import postgres_checkpointer
    from cs_agent.services import records

    _, Session = db
    t0 = datetime(2026, 10, 21, 0, 0, tzinfo=UTC)
    clock = {"now": t0}
    monkeypatch.setattr(records, "_now", lambda: clock["now"])
    at = lambda hours: t0 + timedelta(hours=hours)  # noqa: E731
    inquiry = InquiryIn(
        channel="email",
        subject="Transformer dimensions",
        body="What are the dimensions?",
        category=Category.TECH_SPEC,
        received_at=t0,
    )

    with postgres_checkpointer(TEST_DATABASE_URL) as saver:
        service = _db_service(Session, saver)
        tid = service.submit(inquiry).ticket_id
        target_h = (service.get(tid).sla_due_at - t0).total_seconds() / 3600
        clock["now"] = at(2)
        assert service.act(tid, ReviewIn(action=ReviewAction.APPROVE)).status == (
            TicketStatus.WAITING_CUSTOMER
        )
        with Session() as s:
            assert s.get(Ticket, tid).waiting_since == at(2)

        def row(hours):
            [r] = service.work_list(now=at(hours))
            return r

        assert row(12)["sla_ratio"] == row(2)["sla_ratio"] == round(2 / target_h, 3)
        clock["now"] = at(12)
        service.reply(tid, inquiry.model_copy(update={"body": "Model is TRF-OIL-1000."}))
        with Session() as s:
            ticket = s.get(Ticket, tid)
            assert (ticket.waiting_since, ticket.customer_wait_hours) == (None, 10)
        assert row(20)["sla_ratio"] == round((20 - 10) / target_h, 3)
        assert row(20)["sla_due_at"] == at(target_h + 10)
        assert service.get(tid).sla_due_at == at(target_h + 10)


@needs_db
def test_reply_preview_survives_restart_and_is_sent_without_retranslation(db, monkeypatch):
    from cs_agent.agents import drafting
    from cs_agent.graph.builder import postgres_checkpointer
    from cs_agent.llm.router import LLMRouter
    from cs_agent.schemas import CheckResult

    _, Session = db
    source = "Please confirm the product specifications before proceeding with installation."
    translated = (
        "Veuillez confirmer les spécifications du produit avant de procéder à l’installation."
    )
    calls = []

    def translate(*args):
        calls.append(args[0])
        return translated

    def forbidden(*args):
        raise AssertionError("Sending must reuse the previously displayed translation")

    monkeypatch.setattr(drafting, "translate_reply", translate)
    agents = {
        "write_draft": lambda *a, **k: Draft(text=source, slots={"draft_language": "en"}),
        "verify": lambda *a, **k: [CheckResult(name="test", passed=True)],
        "translate_reply": forbidden,
    }
    inquiry = InquiryIn(
        channel="email",
        language="fr",
        category=Category.TECH_SPEC,
        product_code="TRF-OIL-1000",
        body="Please confirm the dimensions.",
        provided_fields={"application": "substation"},
    )
    with postgres_checkpointer(TEST_DATABASE_URL) as saver:
        service = _db_service(Session, saver, **agents)
        row = service.submit(inquiry)
        preview = service.prepare_reply(row.ticket_id, source, LLMRouter(Settings(_env_file=None)))
        assert service.get(row.ticket_id).final_reply is None
        assert service._state(row.ticket_id).next == ("review",)
    with postgres_checkpointer(TEST_DATABASE_URL) as saver:
        restored = _db_service(Session, saver, **agents)
        result = restored.act(
            row.ticket_id,
            ReviewIn(
                action="approve",
                reviewer="tester",
                reply_preview_id=preview["preview_id"],
            ),
        )
        assert result.status == TicketStatus.APPROVED
        assert result.final_reply == translated
        assert result.approved_reply == source
        assert calls == [source]
