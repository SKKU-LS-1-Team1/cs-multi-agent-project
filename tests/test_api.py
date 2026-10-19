from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

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
    with TestClient(create_app(llm=LLMRouter(Settings(_env_file=None)))) as c:
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
    assert len(client.app.state.tickets.cases) == 1  # 승인 건은 사례로 남는다


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
