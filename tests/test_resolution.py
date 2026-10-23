"""Confirmed completion input survives persistence and becomes grounded case memory."""

import pytest
from test_api import INQUIRY
from test_api import client as client
from test_db import TEST_DATABASE_URL, _db_service, needs_db
from test_db import db as db

from cs_agent.agents.case_memory import build_case, case_evidence
from cs_agent.domain import FeedbackReason, ReviewAction, TicketStatus
from cs_agent.schemas import Draft, Extraction, InquiryIn, ResolveIn, ReviewIn
from cs_agent.services.tickets import InvalidAction


def result(**changes):
    return {
        "outcome": "resolved",
        "cause": "Confirmed loose connection",
        "action": "Reconnected terminal",
        "result": "Customer confirmed normal operation",
        "verification": "Customer ran equipment for 24 hours",
        "confirmed_by": "담당자",
        "references": [{"id": "DOC-1#2", "label": "Service guide", "kind": "document"}],
        **changes,
    }


def approved(client):
    tid = client.post("/api/tickets", json=INQUIRY).json()["ticket_id"]
    assert (
        client.post(f"/api/tickets/{tid}/action", json={"action": "approve"}).json()["status"]
        == "APPROVED"
    )
    return tid


@pytest.mark.parametrize("outcome", ["resolved", "provided"])
def test_explicit_resolution_replaces_draft_guesses_and_is_retrievable(client, outcome):
    tid = approved(client)
    response = client.post(f"/api/tickets/{tid}/resolve", json=result(outcome=outcome))
    assert response.status_code == 200
    final = response.json()
    assert final["status"] == "RESOLVED"
    assert final["resolution"]["confirmed_at"]
    assert final["resolution"]["superseded"] is False
    assert final["resolution"]["cause"] == result()["cause"]
    service = client.app.state.tickets
    assert service.records.tickets[tid]["resolution"] == final["resolution"]
    case = service.records.cases[0]
    assert case["cause"] == result()["cause"]
    assert case["action"] == result()["action"]
    assert result()["result"] in case_evidence(case).text
    assert result()["verification"] in case_evidence(case).text
    assert case["final_reply"] == final["final_reply"]
    assert "DOC-1#2" in case["cited"]
    assert client.post(f"/api/tickets/{tid}/resolve", json=result(outcome=outcome)).json() == final
    assert len(service.records.cases) == 1
    assert (
        client.post(f"/api/tickets/{tid}/resolve", json=result(action="Different")).status_code
        == 409
    )


def test_unconfirmed_closure_is_saved_but_never_learned(client):
    tid = approved(client)
    response = client.post(f"/api/tickets/{tid}/resolve", json=result(outcome="unconfirmed"))
    assert response.json()["status"] == "RESOLVED"
    assert response.json()["resolution"]["outcome"] == "unconfirmed"
    service = client.app.state.tickets
    assert service.records.live_cases() == []
    with pytest.raises(ValueError, match="Unconfirmed"):
        build_case(service._state(tid).values)


@pytest.mark.parametrize(
    "change",
    [
        {"cause": " "},
        {"action": ""},
        {"verification": ""},
        {"confirmed_by": ""},
        {"outcome": "guess"},
        {"result": "x" * 20001},
    ],
)
def test_invalid_completion_does_not_close_ticket(client, change):
    tid = approved(client)
    assert client.post(f"/api/tickets/{tid}/resolve", json=result(**change)).status_code == 422
    assert client.get(f"/api/tickets/{tid}").json()["status"] == "APPROVED"


def test_reopen_preserves_superseded_result_and_deactivates_case(client):
    tid = approved(client)
    service = client.app.state.tickets
    old = service.resolve(tid, ResolveIn(**result())).resolution
    reopened = service.reply(tid, InquiryIn(**{**INQUIRY, "body": "The issue has returned."}))
    assert reopened.resolution.superseded
    assert reopened.resolution.confirmed_at == old.confirmed_at
    assert service.records.live_cases() == []
    assert service.records.tickets[tid]["resolution"]["superseded"]
    service.act(tid, ReviewIn(action=ReviewAction.APPROVE))
    final = service.resolve(tid, ResolveIn(**result(cause="A different confirmed cause")))
    assert not final.resolution.superseded
    assert service.records.live_cases()[0]["cause"] == "A different confirmed cause"


@pytest.mark.parametrize("fail_method", ["save_state", "save_case"])
def test_same_completion_retry_recovers_after_storage_failure(client, monkeypatch, fail_method):
    tid = approved(client)
    service = client.app.state.tickets
    original = getattr(service.records, fail_method)
    calls = 0

    def fail_once(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("temporary storage failure")
        return original(*args, **kwargs)

    monkeypatch.setattr(service.records, fail_method, fail_once)
    with pytest.raises(RuntimeError, match="temporary"):
        service.resolve(tid, ResolveIn(**result()))
    fixed = service.resolve(tid, ResolveIn(**result()))
    assert fixed.status == TicketStatus.RESOLVED
    assert len(service.records.live_cases()) == 1
    assert service.records.tickets[tid]["resolution"]["cause"] == result()["cause"]
    service.resolve(tid, ResolveIn(**result()))
    if fail_method == "save_case":
        assert calls == 2  # same-result retries do not re-embed a successfully saved case


def test_case_masks_confirmed_fields_and_keeps_original_edit_feedback():
    original = ReviewIn(
        action=ReviewAction.EDIT_APPROVE,
        edited_text="Confirmed answer",
        feedback="Wrong value user@example.com",
        feedback_reason=FeedbackReason.FACT_ERROR,
    )
    state = {
        "ticket_id": "T-MASK",
        "inquiry": InquiryIn(channel="email", body="Question"),
        "draft": Draft(
            text="AI guess", slots={"cause": "Guessed cause", "action": "Guessed action"}
        ),
        "review": ReviewIn(action=ReviewAction.APPROVE),
        "approval_review": original.model_dump(mode="json"),
        "approved_reply": "Confirmed answer",
        "final_reply": "Actually sent answer",
        "extraction": Extraction(serial_no="ABC12345"),
        "resolution": result(
            cause="Connection ABC12345",
            action="Replaced at COMPANY_1_2",
            result="Reply from user@example.com",
            verification="S/N: ABC12345",
        ),
    }
    case = build_case(state)
    assert case["edited"] and case["source_fix_needed"]
    assert case["review_action"] == "edit_approve"
    assert case["feedback"] == "Wrong value **MASKED**"
    assert "Guessed" not in case["text"]
    for secret in ["ABC12345", "COMPANY_1_2", "user@example.com"]:
        assert secret not in case["text"]
    assert case["final_reply"] == "Actually sent answer"


def test_manual_override_requires_reviewer_identity(client):
    tid = client.post("/api/tickets", json=INQUIRY).json()["ticket_id"]
    assert (
        client.post(
            f"/api/tickets/{tid}/action",
            json={"action": "approve", "acknowledged_failures": True, "reviewer": " "},
        ).status_code
        == 409
    )


@needs_db
def test_resolution_survives_database_and_checkpointer_restart(db):
    from sqlalchemy import select

    from cs_agent.db.models import ResolutionCase, ReviewRow, Ticket
    from cs_agent.graph.builder import postgres_checkpointer

    _, Session = db
    with postgres_checkpointer(TEST_DATABASE_URL) as saver:
        service = _db_service(Session, saver)
        tid = service.submit(InquiryIn(**INQUIRY)).ticket_id
        service.act(
            tid, ReviewIn(action=ReviewAction.APPROVE, reviewer="staff", acknowledged_failures=True)
        )
        done = service.resolve(tid, ResolveIn(**result()))
        with Session() as session:
            stored = session.get(Ticket, tid)
            assert stored.resolution["verification"] == result()["verification"]
            case = session.scalar(select(ResolutionCase).where(ResolutionCase.ticket_id == tid))
            assert case.cause == result()["cause"]
            assert result()["result"] in case.text
            audit = session.scalar(select(ReviewRow).where(ReviewRow.ticket_id == tid))
            assert audit.acknowledged_failures is True and audit.reviewer == "staff"
    with postgres_checkpointer(TEST_DATABASE_URL) as saver:
        restored = _db_service(Session, saver)
        assert restored.get(tid).resolution == done.resolution
        assert restored.resolve(tid, ResolveIn(**result())).resolution == done.resolution
        with pytest.raises(InvalidAction):
            restored.resolve(tid, ResolveIn(**result(cause="changed")))


def test_saved_final_candidate_citations_do_not_reuse_original_draft():
    from cs_agent.schemas import CheckResult
    from cs_agent.services.records import draft_versions

    state = {
        "ticket_id": "T-CITED",
        "inquiry": InquiryIn(channel="email", body="Question"),
        "draft": Draft(text="Original [DOC-OLD#1]", cited=["DOC-OLD#1"]),
        "approval_text": "Staff final answer",
        "approved_reply": "Staff final answer",
        "approval_cited": [],
        "final_reply": "Customer final answer",
        "checks": [CheckResult(name="final", passed=True)],
        "review": ReviewIn(action=ReviewAction.EDIT_APPROVE, edited_text="Staff final answer"),
        "resolution": result(references=[]),
    }
    rows = draft_versions(state)
    assert rows[0]["text"] == "Staff final answer"
    assert rows[0]["cited"] == []
    assert rows[0]["checks"][0]["name"] == "final"
    assert build_case(state)["cited"] == []
    state["draft"] = None
    manual = draft_versions(state)
    assert manual[0]["text"] == "Staff final answer"
    assert manual[0]["model"] == "staff_review"


def test_confirmed_escalation_does_not_invent_a_sent_customer_answer():
    state = {
        "ticket_id": "T-ESC",
        "inquiry": InquiryIn(channel="email", body="Question"),
        "draft": Draft(text="Unsent AI draft"),
        "review": ReviewIn(action=ReviewAction.ESCALATE, edited_text="Internal department request"),
        "final_reply": None,
        "resolution": result(),
    }
    case = build_case(state)
    assert case["final_reply"] == ""
    assert "Unsent AI draft" not in case["text"]
    assert "Internal department request" not in case["text"]
