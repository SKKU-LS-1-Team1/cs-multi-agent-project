"""이관 후 진행 보고·자료 요청·판정은 분리하고 고객 안내에는 공개 단계만 쓴다."""

import json
from copy import deepcopy
from types import SimpleNamespace
from uuid import uuid4

import pytest
from test_api import INQUIRY
from test_api import client as client
from test_db import db as db
from test_db import needs_db
from test_progress_service import notices as notices
from test_specialists import reply, request

from cs_agent.agents.progress import ProgressError, _facts
from cs_agent.agents.specialist_followup import (
    current_followup,
    missing_fields,
    read_replies,
    source_version,
    validate_reading,
)
from cs_agent.followup_schemas import FollowupReading

TEXT = "Reproduction testing is in progress. Please provide the event logs."
FINAL = "Final finding: the supplied unit is defective. Replacement is recommended."


def reading(rid, text=TEXT, *, final=False):
    return {
        "steps": []
        if final
        else [
            {
                "stage": "reproduction_test",
                "status": "in_progress",
                "reply_id": rid,
                "evidence": text,
            }
        ],
        "requested_fields": [] if final else [{"field": "logs", "reply_id": rid, "evidence": text}],
        "conclusion": {"reply_id": rid, "evidence": text} if final else None,
        "needs_review": False,
    }


def setup_investigation(client, text=TEXT, *, final=False, fail=False):
    tid = client.post(
        "/api/tickets", json={**INQUIRY, "customer_id": "C-FOLLOW", "language": "fr"}
    ).json()["ticket_id"]
    service = client.app.state.tickets
    body = reply(text=text)

    def reader(state, requests):
        if fail:
            raise RuntimeError("provider failure")
        return reading(body["reply_id"], text, final=final)

    service.specialist_reader = reader
    req = request(to_dept="QA_CLAIM")
    base = f"/api/tickets/{tid}"
    assert client.post(base + "/specialist-requests", json=req).status_code == 200
    out = client.post(base + f"/specialist-requests/{req['request_id']}/reply", json=body)
    assert out.status_code == 200
    return base, req, body, out.json()


def confirmation(out, body):
    return {
        "source_version": out["specialist_followup"]["source_version"],
        "reviewer": "Staff",
        "finding": {"reply_id": body["reply_id"], "evidence": body["text"]},
    }


def test_reply_evidence_must_exist_and_requested_fields_must_be_defined():
    requests = [{"reply": {"reply_id": "R", "text": TEXT}}]
    result = FollowupReading.model_validate(reading("R"))
    assert validate_reading(result, requests, {"logs": "event logs"})["steps"]
    with pytest.raises(ValueError, match="Unknown requested"):
        validate_reading(result, requests, {})
    with pytest.raises(ValueError, match="Unsupported"):
        validate_reading(
            result,
            [{"reply": {"reply_id": "R", "text": "No test was performed."}}],
            {"logs": "logs"},
        )


def test_customer_claim_cannot_be_used_as_specialist_evidence_and_judge_rejects_inference():
    raw = reading("R")
    calls = []
    llm = SimpleNamespace(
        enabled=True,
        write=lambda *args: json.dumps(raw),
        judge=lambda *args: (
            calls.append(args) or SimpleNamespace(answer="no", confidence=1, model="judge")
        ),
    )
    with pytest.raises(ValueError, match="Unverified"):
        read_replies(
            {"inquiry": {"body": "Product is defective"}},
            [{"reply": {"reply_id": "R", "text": TEXT}}],
            {"logs": "logs"},
            llm,
        )
    assert calls


def test_reading_wrapped_in_markdown_fence_is_accepted():
    """Gemini write() 가 ```json 으로 감싸 돌려줘도 해석한다 (운영에서 매번 실패했다)."""
    raw = reading("R")
    llm = SimpleNamespace(
        enabled=True,
        write=lambda *args: "```json\n" + json.dumps(raw) + "\n```",
        judge=lambda *args: SimpleNamespace(answer="yes", confidence=1, model="judge"),
    )
    out = read_replies(
        {"inquiry": {"body": "Unit trips"}},
        [{"reply": {"reply_id": "R", "text": TEXT}}],
        {"logs": "logs"},
        llm,
    )
    assert out["steps"][0]["stage"] == "reproduction_test"


def test_provided_fields_are_not_requested_again_and_new_customer_data_invalidates_reading():
    state = {
        "inquiry": {"provided_fields": {"logs": "attached"}},
        "extraction": {"field_values": {}},
        "specialist_followup": None,
    }
    assert missing_fields(reading("R"), state) == []
    requests = [{"to_dept": "QA_CLAIM", "reply": {"reply_id": "R", "text": TEXT}}]
    state["specialist_followup"] = {
        "source_version": source_version(state, requests),
        "reading": reading("R"),
    }
    assert current_followup(state, requests)["reading"]
    state["inquiry"]["provided_fields"]["logs"] = "withdrawn"
    assert current_followup(state, requests)["reading"] is None


def test_progress_facts_allow_only_public_step_codes_not_raw_specialist_content():
    facts = [
        {
            "ticket_id": "T-1",
            "status": "READY_FOR_REVIEW",
            "investigation": {
                "status": "in_progress",
                "private_summary": "secret serial 12345",
                "steps": [
                    {"stage": "serial_trace", "status": "completed", "evidence": "private data"}
                ],
            },
        }
    ]
    clean = _facts(facts)
    assert clean[0]["investigation"] == {
        "status": "in_progress",
        "steps": [{"stage": "serial_trace", "status": "completed"}],
    }
    assert "private" not in json.dumps(clean)
    facts[0]["investigation"]["steps"][0]["stage"] = "warranty_approved"
    with pytest.raises(ProgressError):
        _facts(facts)


def test_intermediate_reply_remains_investigation_and_blocks_final_approval(client, notices):
    base, req, body, out = setup_investigation(client)
    f = out["specialist_followup"]
    assert f["status"] == "in_progress"
    assert f["missing_fields"] == ["logs"]
    assert (
        client.post(
            base + "/action", json={"action": "approve", "expected_specialist_revision": 2}
        ).status_code
        == 409
    )
    service, generated, _ = notices
    notice = client.post(
        base + "/progress-notices",
        json={"notice_id": str(uuid4()), "ticket_ids": [out["ticket_id"]]},
    )
    assert notice.status_code == 200
    assert generated[-1][0]["investigation"]["steps"] == [
        {"stage": "reproduction_test", "status": "in_progress"}
    ]
    assert TEXT not in json.dumps(generated)


def test_final_finding_requires_explicit_staff_confirmation_and_rejects_stale_version(client):
    base, req, body, out = setup_investigation(client, FINAL, final=True)
    assert out["specialist_followup"]["status"] == "in_progress"
    change = confirmation(out, body)
    wrong = {**change, "source_version": "stale"}
    assert client.post(base + "/specialist-followup/confirm", json=wrong).status_code == 409
    wrong = deepcopy(change)
    wrong["finding"]["evidence"] = "Warranty was approved."
    assert client.post(base + "/specialist-followup/confirm", json=wrong).status_code == 409
    confirmed = client.post(base + "/specialist-followup/confirm", json=change)
    assert confirmed.status_code == 200
    assert confirmed.json()["specialist_followup"]["status"] == "confirmed"
    assert confirmed.json()["status"] == out["status"]
    assert client.post(base + "/specialist-followup/confirm", json=change).status_code == 200
    assert (
        client.post(base + "/specialist-requests", json=request(to_dept="FIELD_SVC")).status_code
        == 200
    )
    fresh = client.get(base).json()["specialist_followup"]
    assert fresh["status"] == "in_progress" and fresh["confirmation"] is None
    assert client.post(base + "/specialist-followup/confirm", json=change).status_code == 409


def test_reader_failure_keeps_reply_and_allows_manual_finding_confirmation(client):
    base, req, body, out = setup_investigation(client, FINAL, fail=True)
    assert out["specialist_requests"][0]["reply"]["text"] == FINAL
    assert out["specialist_followup"]["error"]
    assert out["specialist_followup"]["reading"] is None
    confirmed = client.post(base + "/specialist-followup/confirm", json=confirmation(out, body))
    assert confirmed.status_code == 200
    assert confirmed.json()["specialist_followup"]["status"] == "confirmed"


def test_pending_other_department_prevents_finding_confirmation(client):
    base, req, body, out = setup_investigation(client, FINAL, final=True)
    client.post(base + "/specialist-requests", json=request(to_dept="CERT"))
    updated = client.get(base).json()
    assert (
        client.post(
            base + "/specialist-followup/confirm", json=confirmation(updated, body)
        ).status_code
        == 409
    )


def test_confirmation_invalidates_old_customer_notice_and_customer_reply_invalidates_finding(
    client, notices
):
    base, req, body, out = setup_investigation(client, FINAL, final=True)
    notice = client.post(
        base + "/progress-notices",
        json={"notice_id": str(uuid4()), "ticket_ids": [out["ticket_id"]]},
    ).json()
    confirmed = client.post(
        base + "/specialist-followup/confirm", json=confirmation(out, body)
    ).json()
    stale_notice = client.post(
        base + f"/progress-notices/{notice['notice_id']}/approve",
        json={"reviewer": "Staff", "edited_text": "Your ticket is under review."},
    )
    assert stale_notice.status_code == 409
    service = client.app.state.tickets
    state = service._state(out["ticket_id"]).values
    assert current_followup(state, state["specialist_requests"])["status"] == "confirmed"
    from cs_agent.schemas import InquiryIn

    updated = service.reply(
        out["ticket_id"],
        InquiryIn(**{**INQUIRY, "body": "Correction: another product is affected."}),
    )
    assert updated.specialist_followup["status"] == "in_progress"
    assert updated.specialist_followup["confirmation"] is None
    assert confirmed["specialist_followup"]["confirmation"]["finding"]["evidence"] == FINAL


@needs_db
def test_postgres_followup_confirmation_survives_checkpointer_reopening(db):
    from test_db import TEST_DATABASE_URL, _db_service

    from cs_agent.followup_schemas import FollowupConfirmation
    from cs_agent.graph.builder import postgres_checkpointer
    from cs_agent.schemas import InquiryIn, SpecialistReplyIn, SpecialistRequestIn

    _, Session = db
    with postgres_checkpointer(TEST_DATABASE_URL) as saver:
        service = _db_service(Session, saver)
        tid = service.submit(InquiryIn(**INQUIRY)).ticket_id
        req = SpecialistRequestIn(**request(to_dept="QA_CLAIM"))
        body = SpecialistReplyIn(**reply(text=FINAL))
        service.add_specialist_request(tid, req)
        out = service.add_specialist_reply(tid, str(req.request_id), body)
        service.confirm_specialist_finding(
            tid,
            FollowupConfirmation(
                source_version=out.specialist_followup["source_version"],
                reviewer="Staff",
                finding={"reply_id": str(body.reply_id), "evidence": FINAL},
            ),
        )
    with postgres_checkpointer(TEST_DATABASE_URL) as saver:
        restored = _db_service(Session, saver).get(tid)
        assert restored.specialist_followup["status"] == "confirmed"
        assert restored.specialist_followup["confirmation"]["finding"]["evidence"] == FINAL


def test_reader_timeout_returns_without_waiting_for_provider_and_releases_when_done(monkeypatch):
    from concurrent.futures import Future, TimeoutError

    from cs_agent.agents import specialist_followup as agent

    future = Future()
    waits = []
    monkeypatch.setattr(agent._POOL, "submit", lambda *args: future)

    def timeout(*, timeout):
        waits.append(timeout)
        raise TimeoutError()

    monkeypatch.setattr(future, "result", timeout)
    with pytest.raises(TimeoutError):
        read_replies({}, [], {}, SimpleNamespace(enabled=True))
    assert waits == [agent.TIMEOUT_S]
    future.set_result(None)  # The outstanding call owns capacity until it actually finishes.


def test_confirmation_does_not_erase_already_sent_information_request(client):
    base, req, body, out = setup_investigation(client, FINAL, final=True)
    service = client.app.state.tickets
    tid = out["ticket_id"]
    service.graph.update_state(
        service._config(tid),
        {
            "status": "WAITING_CUSTOMER",
            "pending": "info_request",
            "approved_reply": "Please send the logs.",
            "final_reply": "Veuillez envoyer les journaux.",
        },
        as_node="finish",
    )
    out = client.get(base).json()
    confirmed = client.post(base + "/specialist-followup/confirm", json=confirmation(out, body))
    assert confirmed.status_code == 200
    assert confirmed.json()["final_reply"] == "Veuillez envoyer les journaux."
    assert confirmed.json()["approved_reply"] == "Please send the logs."
