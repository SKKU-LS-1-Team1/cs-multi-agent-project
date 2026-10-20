from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from stubs import ANALYSIS

from cs_agent.config import Settings
from cs_agent.llm.router import LLMRouter
from cs_agent.main import create_app

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
