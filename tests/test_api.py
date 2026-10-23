from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from stubs import ANALYSIS

from cs_agent.config import Settings
from cs_agent.llm.router import LLMRouter
from cs_agent.main import create_app
from cs_agent.schemas import CheckResult

INQUIRY = {
    "channel": "email",
    "customer_tier": "GOLD",
    "language": "en",
    "subject": "Dimensions of TRF-OIL-1000",
    "body": "What are the dimensions and weight of TRF-OIL-1000?",
    "category": "TECH_SPEC",
    "provided_fields": {"application": "substation"},
}


@pytest.fixture
def client():
    with TestClient(
        create_app(
            llm=LLMRouter(Settings(_env_file=None)),
            agents=ANALYSIS,
            storage="memory",
            retrievers=(None, None),
        )
    ) as c:
        yield c


def test_health(client):
    assert client.get("/api/health").json()["status"] == "ok"


def test_submit_review_approve_resolve(client):
    res = client.post("/api/tickets", json=INQUIRY)
    assert res.status_code == 201
    ticket = res.json()
    assert ticket["status"] == "READY_FOR_REVIEW"
    assert (ticket["priority"], ticket["assigned_dept"]) == ("P4", "TS_TRF")
    assert ticket["draft"]["text"]
    tid = ticket["ticket_id"]

    assert client.get(f"/api/tickets/{tid}").json()["ticket_id"] == tid
    approved = client.post(f"/api/tickets/{tid}/action", json={"action": "approve"})
    assert approved.json()["status"] == "APPROVED"
    resolved = client.post(f"/api/tickets/{tid}/resolve")
    assert resolved.json()["status"] == "RESOLVED"
    assert len(client.app.state.tickets.records.cases) == 1  # 승인 건은 사례로 남는다


def test_api_exposes_english_review_and_approved_customer_reply():
    from cs_agent.agents.drafting import TranslationError

    attempts = []

    def translate(text, source, target, llm):
        attempts.append((text, source, target))
        if len(attempts) == 1:
            raise TranslationError("Temporary translation failure")
        return "Respuesta aprobada."

    with TestClient(
        create_app(
            llm=LLMRouter(Settings(_env_file=None)),
            agents={
                **ANALYSIS,
                "translate_reply": translate,
                # 이 검사는 번역 실패·재시도와 고객 언어 노출을 검증한다.
                "verify": lambda *a: [CheckResult(name="translation_test", passed=True)],
            },
            storage="memory",
            retrievers=(None, None),
        )
    ) as client:
        ticket = client.post("/api/tickets", json={**INQUIRY, "language": "es"}).json()
        tid = ticket["ticket_id"]
        assert ticket["draft"]["slots"]["draft_language"] == "en"
        assert ticket["final_reply"] is None
        assert not attempts  # 검토 전에 번역하지 않음
        held = client.post(
            f"/api/tickets/{tid}/action",
            json={"action": "edit_approve", "edited_text": "Approved English reply."},
        ).json()
        assert held["status"] == "ON_HOLD"
        assert held["approved_reply"] == "Approved English reply."
        assert held["translation_error"]
        assert held["final_reply"] is None
        assert client.post(f"/api/tickets/{tid}/resolve").status_code == 409
        done = client.post(f"/api/tickets/{tid}/action", json={"action": "approve"}).json()
        assert attempts == [("Approved English reply.", "en", "es")] * 2
        assert done["status"] == "APPROVED"
        assert done["final_reply"] == "Respuesta aprobada."
        assert done["final_reply_language"] == "es"
        assert done["translation_error"] is None
        assert client.get(f"/api/tickets/{tid}").json()["final_reply"] == done["final_reply"]
        assert client.post(f"/api/tickets/{tid}/resolve").status_code == 200
        assert client.app.state.tickets.records.cases[0]["final_reply"] == done["final_reply"]


def test_llm_calls_are_grouped_per_ticket(client, monkeypatch):
    from cs_agent.llm import router, tracing

    seen = []
    real_trace = tracing.trace

    def spy(task, model, prompt, **meta):
        seen.append((task, tracing._ticket_id.get()))
        return real_trace(task, model, prompt, **meta)

    monkeypatch.setattr(router, "trace", spy)
    tid = client.post("/api/tickets", json=INQUIRY).json()["ticket_id"]
    client.post(f"/api/tickets/{tid}/action", json={"action": "rewrite", "feedback": "짧게"})

    assert [t for t, _ in seen] == ["draft", "draft"]
    assert {ticket for _, ticket in seen} == {tid}


def test_errors(client):
    assert client.get("/api/tickets/NOPE").status_code == 404
    assert client.post("/api/tickets/NOPE/action", json={"action": "approve"}).status_code == 404

    tid = client.post("/api/tickets", json=INQUIRY).json()["ticket_id"]
    assert client.post(f"/api/tickets/{tid}/resolve").status_code == 409  # 아직 승인 전
    client.post(f"/api/tickets/{tid}/action", json={"action": "reject"})
    assert client.post(f"/api/tickets/{tid}/action", json={"action": "approve"}).status_code == 409


def test_work_list_sorted_by_sla_and_filtered(client):
    old = {**INQUIRY, "received_at": (datetime.now(UTC) - timedelta(hours=200)).isoformat()}
    new_id = client.post("/api/tickets", json=INQUIRY).json()["ticket_id"]
    old_id = client.post("/api/tickets", json=old).json()["ticket_id"]

    rows = client.get("/api/tickets").json()

    assert [r["ticket_id"] for r in rows] == [old_id, new_id]
    assert rows[0]["at_risk"] is True  # 200h / 240h ≥ 75%
    assert rows[1]["at_risk"] is False
    assert client.get("/api/tickets?dept=NONE").json() == []


def test_customer_reply_resumes_same_ticket(client):
    first = client.post("/api/tickets", json={**INQUIRY, "thread_ref": "mail-1"}).json()
    tid = first["ticket_id"]
    client.post(f"/api/tickets/{tid}/action", json={"action": "rewrite", "feedback": "짧게"})

    reply = {"channel": "email", "body": "Also the weight, please.", "thread_ref": "mail-1"}
    again = client.post("/api/tickets", json=reply).json()

    assert again["ticket_id"] == tid  # 새 티켓이 아니라 같은 티켓
    assert again["status"] == "READY_FOR_REVIEW"
    values = client.app.state.tickets.graph.get_state({"configurable": {"thread_id": tid}}).values
    assert values["followups"] == 1
    assert values["review"] is None  # 지난 상담원 피드백은 새 답변에 섞이지 않는다
    assert values["inquiry"].body.endswith("Also the weight, please.")
    assert values["inquiry"].category == "TECH_SPEC"  # 원문 값 유지

    client.post(f"/api/tickets/{tid}/action", json={"action": "approve"})
    client.post(f"/api/tickets/{tid}/resolve")
    records = client.app.state.tickets.records
    assert [c["active"] for c in records.cases] == [True]

    reopened = client.post("/api/tickets", json={**reply, "body": "It tripped again."}).json()
    assert (reopened["ticket_id"], reopened["status"]) == (tid, "READY_FOR_REVIEW")
    assert [c["active"] for c in records.cases] == [False]  # 다시 열린 문의의 사례는 검색에서 뺀다


def test_records_keep_draft_versions_and_reviews(client):
    tid = client.post("/api/tickets", json=INQUIRY).json()["ticket_id"]
    client.post(f"/api/tickets/{tid}/action", json={"action": "rewrite", "feedback": "짧게"})
    client.post(f"/api/tickets/{tid}/action", json={"action": "approve"})

    records = client.app.state.tickets.records
    assert records.tickets[tid]["status"] == "APPROVED"
    assert records.tickets[tid]["assigned_dept"] == "TS_TRF"
    assert [r.action for r in records.reviews[tid]] == ["rewrite", "approve"]
    assert records.drafts[tid][0]["kind"] == "draft"


def _app_with(monkeypatch, **env):
    from cs_agent.config import get_settings

    for key, value in env.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()
    monkeypatch.setattr("cs_agent.main.get_settings", get_settings)
    return create_app(
        llm=LLMRouter(Settings(_env_file=None)), agents=ANALYSIS, retrievers=(None, None)
    )


def test_local_falls_back_to_memory_without_db_or_redis(monkeypatch):
    app = _app_with(
        monkeypatch,
        APP_ENV="local",
        DATABASE_URL="postgresql+psycopg://cs:cs@127.0.0.1:1/cs",
        REDIS_URL="redis://127.0.0.1:1/0",
        ANALYSIS_RETRY_INTERVAL_S="0",
    )
    try:
        with TestClient(app) as c:
            assert c.app.state.sessionmaker is None
            assert c.app.state.chat_sessions.client is None
            assert c.post("/api/tickets", json=INQUIRY).status_code == 201
    finally:
        from cs_agent.config import get_settings

        get_settings.cache_clear()


def test_prod_refuses_to_start_without_db(monkeypatch):
    app = _app_with(
        monkeypatch,
        APP_ENV="prod",
        DATABASE_URL="postgresql+psycopg://cs:cs@127.0.0.1:1/cs",
        ANALYSIS_RETRY_INTERVAL_S="0",
    )
    try:
        with pytest.raises(RuntimeError, match="PostgreSQL"), TestClient(app):
            pass
    finally:
        from cs_agent.config import get_settings

        get_settings.cache_clear()


def test_reply_edited_in_customer_language_is_sent_without_translation():
    """상담원이 고객 언어로 직접 고쳐 승인하면 번역하지 않고 그대로 보낸다 (예전에는 보류됐다)."""
    calls = []

    def translate(text, source, target, llm):
        calls.append((source, target))
        return text  # 실제 모델도 같은 글을 돌려준다 → 예전에는 '번역 안 됨' 으로 보류

    with TestClient(
        create_app(
            llm=LLMRouter(Settings(_env_file=None)),
            agents={**ANALYSIS, "translate_reply": translate},
            storage="memory",
            retrievers=(None, None),
        )
    ) as client:
        tid = client.post("/api/tickets", json={**INQUIRY, "language": "es"}).json()["ticket_id"]
        spanish = (
            "Las dimensiones del TRF-OIL-1000 están en la sección 2 de la hoja de datos. "
            "Quedamos atentos a cualquier otra consulta."
        )
        done = client.post(
            f"/api/tickets/{tid}/action", json={"action": "edit_approve", "edited_text": spanish}
        ).json()

    assert done["status"] == "APPROVED"
    assert done["final_reply"] == spanish
    assert calls == []  # 번역을 부르지 않았다


def test_answered_lists_sent_but_unresolved_tickets(client):
    """작업 목록은 APPROVED 를 빼므로 관리자 화면은 완료할 문의를 /answered 로 찾는다 (CSA-61)."""
    tid = client.post("/api/tickets", json=INQUIRY).json()["ticket_id"]
    assert client.get("/api/tickets/answered").json() == []

    client.post(f"/api/tickets/{tid}/action", json={"action": "approve"})
    assert client.get("/api/tickets/answered").json() == [tid]
    assert tid not in [r["ticket_id"] for r in client.get("/api/tickets").json()]

    client.post(f"/api/tickets/{tid}/resolve")
    assert client.get("/api/tickets/answered").json() == []


@pytest.fixture
def preview_client():
    from cs_agent.schemas import Draft

    with TestClient(
        create_app(
            llm=LLMRouter(Settings(_env_file=None)),
            storage="memory",
            retrievers=(None, None),
            agents={
                **ANALYSIS,
                "write_draft": lambda *a, **k: Draft(
                    text=(
                        "Please confirm the product specifications "
                        "before proceeding with installation."
                    ),
                    slots={"draft_language": "en"},
                    model="test",
                ),
                "verify": lambda *a, **k: [CheckResult(name="test", passed=True)],
            },
        )
    ) as client:
        yield client


def test_explicit_reply_preview_does_not_send_and_send_reuses_exact_preview(
    preview_client, monkeypatch
):
    client = preview_client
    from cs_agent.agents import drafting

    calls = []

    def translate(text, source, target, llm):
        calls.append((text, source, target))
        return "Exact preview shown to the staff."

    monkeypatch.setattr(drafting, "translate_reply", translate)
    row = client.post("/api/tickets", json=INQUIRY).json()
    tid, text = row["ticket_id"], row["draft"]["text"]
    response = client.post(f"/api/tickets/{tid}/reply-preview", json={"text": text})
    assert response.status_code == 200, response.text
    preview = response.json()
    same = client.post(f"/api/tickets/{tid}/reply-preview", json={"text": text}).json()
    assert same["preview_id"] == preview["preview_id"]
    current = client.get(f"/api/tickets/{tid}").json()
    assert current["status"] == row["status"]
    assert current["final_reply"] is None
    sent = client.post(
        f"/api/tickets/{tid}/action",
        json={"action": "approve", "reply_preview_id": preview["preview_id"]},
    )
    assert sent.status_code == 200, sent.text
    assert sent.json()["status"] == "APPROVED"
    assert sent.json()["final_reply"] == preview["final_text"]
    assert len(calls) == 1


def test_preview_rejects_edited_source_and_changed_context(preview_client, monkeypatch):
    client = preview_client
    from cs_agent.agents import drafting

    monkeypatch.setattr(drafting, "translate_reply", lambda *args: "Prepared customer text")
    row = client.post("/api/tickets", json=INQUIRY).json()
    tid, text = row["ticket_id"], row["draft"]["text"]
    preview = client.post(f"/api/tickets/{tid}/reply-preview", json={"text": text}).json()
    edited = client.post(
        f"/api/tickets/{tid}/action",
        json={
            "action": "edit_approve",
            "edited_text": text + " Changed.",
            "reply_preview_id": preview["preview_id"],
        },
    )
    assert edited.status_code == 409
    service = client.app.state.tickets
    service.graph.update_state(service._config(tid), {"customer_revision": 1}, as_node="ready")
    stale = client.post(
        f"/api/tickets/{tid}/action",
        json={
            "action": "approve",
            "reply_preview_id": preview["preview_id"],
        },
    )
    assert stale.status_code == 409
    assert service.get(tid).final_reply is None


def test_preview_translation_failure_keeps_draft_and_review_state(preview_client, monkeypatch):
    client = preview_client
    from cs_agent.agents import drafting

    def fail(*args):
        raise drafting.TranslationError("temporary failure")

    monkeypatch.setattr(drafting, "translate_reply", fail)
    row = client.post("/api/tickets", json=INQUIRY).json()
    tid = row["ticket_id"]
    response = client.post(f"/api/tickets/{tid}/reply-preview", json={"text": row["draft"]["text"]})
    assert response.status_code == 503
    current = client.get(f"/api/tickets/{tid}").json()
    assert current["status"] == row["status"]
    assert current["draft"] == row["draft"]
    assert current["final_reply"] is None


def test_info_request_preview_is_reused_without_second_translation(preview_client, monkeypatch):
    client = preview_client
    from cs_agent.agents import info_request

    calls = []

    def localize(text, language, llm):
        calls.append(text)
        return "Please send the requested information."

    monkeypatch.setattr(info_request, "localize_request", localize)
    row = client.post("/api/tickets", json=INQUIRY).json()
    tid = row["ticket_id"]
    request = client.post(
        f"/api/tickets/{tid}/action",
        json={
            "action": "info_request",
            "info_items": ["serial_no"],
        },
    ).json()
    text = request["info_request"]
    preview_response = client.post(f"/api/tickets/{tid}/reply-preview", json={"text": text})
    assert preview_response.status_code == 200, preview_response.text
    preview = preview_response.json()
    sent = client.post(
        f"/api/tickets/{tid}/action",
        json={
            "action": "approve",
            "reply_preview_id": preview["preview_id"],
        },
    ).json()
    assert sent["status"] == "WAITING_CUSTOMER"
    assert sent["final_reply"] == preview["final_text"]
    assert len(calls) == 1
