"""Existing UI flow: closed discovery, durable timeline and staff-written human replies."""

import pytest
from fastapi.testclient import TestClient
from stubs import ANALYSIS
from test_db import db as db
from test_db import needs_db

from cs_agent.agents.analysis import AnalysisError
from cs_agent.config import Settings
from cs_agent.llm.router import LLMRouter
from cs_agent.main import create_app
from cs_agent.schemas import CheckResult, Draft

TEXT = "Please keep the equipment switched off until our technical team reviews your report."
INQUIRY = {
    "channel": "email",
    "language": "en",
    "category": "DEFECT",
    "subject": "Smoke from product",
    "body": "There is smoke from the iS7 drive.",
    "product_code": "DRV-IS7-0001",
}


@pytest.fixture
def app_client():
    agents = {
        **ANALYSIS,
        "write_draft": lambda *a, **k: Draft(text=TEXT, slots={"draft_language": "en"}),
        "verify": lambda *a, **k: [CheckResult(name="test", passed=True)],
    }
    with TestClient(
        create_app(
            llm=LLMRouter(Settings(_env_file=None)),
            agents=agents,
            storage="memory",
            retrievers=(None, None),
        )
    ) as client:
        yield client


def save_manual(client, row, text=TEXT, **overrides):
    return client.post(
        f"/api/tickets/{row['ticket_id']}/manual-reply",
        json={
            "text": text,
            "reviewer": "tester",
            "expected_customer_revision": row.get("customer_revision", 0),
            "expected_specialist_revision": row.get("specialist_revision", 0),
            "expected_information_reviewed_at": None,
            **overrides,
        },
    )


def test_human_manual_reply_preview_send_and_history(app_client):
    client = app_client
    row = client.post("/api/tickets", json=INQUIRY).json()
    assert row["status"] == "HUMAN_QUEUE"
    saved = save_manual(client, row)
    assert saved.status_code == 200, saved.text
    state = saved.json()
    assert state["manual_reply"] and state["status"] == "ON_HOLD"
    assert state["draft"]["text"] == TEXT and state["final_reply"] is None
    tid = row["ticket_id"]
    snapshot = client.app.state.tickets._state(tid)
    assert snapshot.next == ("review",)
    preview = client.post(f"/api/tickets/{tid}/reply-preview", json={"text": TEXT})
    assert preview.status_code == 200, preview.text
    sent = client.post(
        f"/api/tickets/{tid}/action",
        json={
            "action": "approve",
            "reviewer": "tester",
            "reply_preview_id": preview.json()["preview_id"],
            "expected_customer_revision": 0,
            "expected_specialist_revision": 0,
        },
    )
    assert sent.status_code == 200, sent.text
    result = sent.json()
    assert result["status"] == "APPROVED", result
    assert result["final_reply"] == TEXT
    assert len(result["processing_history"]) == 1
    event = result["processing_history"][0]
    assert event["kind"] == "sent" and event["text"] == TEXT
    assert event["master_text"] == TEXT and event["actor"] == "tester"
    # A subsequent customer reply must not erase the previous answer.
    from cs_agent.schemas import InquiryIn

    reopened = client.app.state.tickets.reply(tid, InquiryIn(**INQUIRY))
    assert reopened.final_reply is None
    assert reopened.processing_history == result["processing_history"]
    assert reopened.manual_reply is False


def test_manual_reply_rejects_stale_context_empty_input_and_closed_ticket(app_client):
    client = app_client
    row = client.post("/api/tickets", json=INQUIRY).json()
    assert save_manual(client, row, expected_customer_revision=2).status_code == 409
    assert save_manual(client, row, text="  ").status_code == 409
    assert save_manual(client, row, reviewer="  ").status_code == 422
    assert save_manual(client, row).status_code == 200
    # AI rewrite is not invoked on missing analysis or a staff-only draft.
    tid = row["ticket_id"]
    assert client.post(f"/api/tickets/{tid}/action", json={"action": "rewrite"}).status_code == 409
    rejected = client.post(
        f"/api/tickets/{tid}/action", json={"action": "reject", "reviewer": "tester"}
    )
    assert rejected.json()["status"] == "REJECTED"
    assert save_manual(client, rejected.json()).status_code == 409
    assert tid in client.get("/api/tickets/closed").json()
    assert rejected.json()["processing_history"][-1]["kind"] == "rejected"


def test_unclassified_human_reply_requires_explicit_confirmation():
    def failed(*args, **kwargs):
        raise AnalysisError("classification_failed")

    agents = {
        **ANALYSIS,
        "classify": failed,
        "verify": lambda *a, **k: [CheckResult(name="test", passed=True)],
    }
    with TestClient(
        create_app(
            llm=LLMRouter(Settings(_env_file=None)),
            agents=agents,
            storage="memory",
            retrievers=(None, None),
        )
    ) as client:
        row = client.post("/api/tickets", json=INQUIRY).json()
        assert row["status"] == "HUMAN_QUEUE" and row["classification"] is None
        saved = save_manual(client, row)
        assert saved.status_code == 200, saved.text
        tid = row["ticket_id"]
        first = client.post(
            f"/api/tickets/{tid}/action",
            json={
                "action": "approve",
                "reviewer": "tester",
                "acknowledged_failures": True,
            },
        ).json()
        assert first["status"] == "ON_HOLD" and first["final_reply"] is None
        assert any(c["name"] == "analysis_unavailable" and not c["passed"] for c in first["checks"])
        assert first["processing_history"] == []
        confirmed = client.post(
            f"/api/tickets/{tid}/action",
            json={
                "action": "approve",
                "reviewer": "tester",
                "acknowledged_failures": True,
            },
        ).json()
        assert confirmed["status"] == "APPROVED"
        assert len(confirmed["processing_history"]) == 1
        assert confirmed["classification"] is None


def test_completed_is_discoverable_and_completion_history_is_idempotent(app_client):
    client = app_client
    row = client.post("/api/tickets", json=INQUIRY).json()
    save_manual(client, row)
    tid = row["ticket_id"]
    sent = client.post(
        f"/api/tickets/{tid}/action", json={"action": "approve", "reviewer": "tester"}
    )
    assert sent.json()["status"] == "APPROVED"
    resolution = {
        "outcome": "unconfirmed",
        "cause": "Not confirmed",
        "action": "Requested specialist review",
        "result": "Case closed without confirmed resolution",
        "verification": "No customer confirmation",
        "confirmed_by": "tester",
        "references": [],
    }
    first = client.post(f"/api/tickets/{tid}/resolve", json=resolution).json()
    second = client.post(f"/api/tickets/{tid}/resolve", json=resolution).json()
    assert first["processing_history"] == second["processing_history"]
    assert [e["kind"] for e in first["processing_history"]] == ["sent", "completed"]
    assert tid in client.get("/api/tickets/closed").json()
    assert tid not in client.get("/api/tickets/answered").json()
    assert tid not in [r["ticket_id"] for r in client.get("/api/tickets").json()]
    assert client.get(f"/api/tickets/{tid}").json()["assignment_history"]


def test_manual_save_is_idempotent_and_does_not_clear_a_checked_preview(app_client):
    row = app_client.post("/api/tickets", json=INQUIRY).json()
    save_manual(app_client, row)
    tid = row["ticket_id"]
    preview = app_client.post(f"/api/tickets/{tid}/reply-preview", json={"text": TEXT}).json()
    assert save_manual(app_client, row).status_code == 200
    again = app_client.post(f"/api/tickets/{tid}/reply-preview", json={"text": TEXT}).json()
    assert again["preview_id"] == preview["preview_id"]


@needs_db
@pytest.mark.parametrize("classified", [True, False])
def test_postgres_manual_flow_timeline_and_closed_discovery_survive_restart(db, classified):
    from test_db import TEST_DATABASE_URL, _db_service

    from cs_agent.graph.builder import postgres_checkpointer
    from cs_agent.schemas import InquiryIn, ManualReplyIn, ResolveIn, ReviewIn

    def failed(*args, **kwargs):
        raise AnalysisError("classification_failed")

    _, Session = db
    agents = {"verify": lambda *a, **k: [CheckResult(name="test", passed=True)]}
    if not classified:
        agents["classify"] = failed
    llm = LLMRouter(Settings(_env_file=None))
    with postgres_checkpointer(TEST_DATABASE_URL) as saver:
        service = _db_service(Session, saver, **agents)
        row = service.submit(InquiryIn(**INQUIRY))
        tid = row.ticket_id
        service.save_manual_reply(
            tid,
            ManualReplyIn(
                text=TEXT,
                reviewer="tester",
                expected_customer_revision=0,
                expected_specialist_revision=0,
            ),
        )
        preview = service.prepare_reply(tid, TEXT, llm)
        assert tid in [r["ticket_id"] for r in service.work_list()]
    with postgres_checkpointer(TEST_DATABASE_URL) as saver:
        service = _db_service(Session, saver, **agents)
        assert service.get(tid).manual_reply
        sent = service.act(
            tid,
            ReviewIn(action="approve", reviewer="tester", reply_preview_id=preview["preview_id"]),
        )
        if not classified:
            assert sent.status == "ON_HOLD"
            assert tid in [r["ticket_id"] for r in service.work_list()]
            sent = service.act(
                tid,
                ReviewIn(
                    action="approve",
                    reviewer="tester",
                    reply_preview_id=preview["preview_id"],
                    acknowledged_failures=True,
                ),
            )
        assert sent.status == "APPROVED"
        assert len(sent.processing_history) == 1
        service.resolve(
            tid,
            ResolveIn(
                outcome="unconfirmed",
                cause="Not confirmed",
                action="Requested specialist review",
                result="Closed without confirmation",
                verification="No customer confirmation",
                confirmed_by="tester",
            ),
        )
    with postgres_checkpointer(TEST_DATABASE_URL) as saver:
        service = _db_service(Session, saver, **agents)
        assert tid in service.closed()
        row = service.get(tid)
        assert [e["kind"] for e in row.processing_history] == ["sent", "completed"]
        assert row.processing_history[0]["text"] == TEXT
        assert row.processing_history[0]["master_text"] == TEXT
