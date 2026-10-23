"""CSA-62: real API path, record recovery, source handoff and stale approval protection."""

from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from test_api import INQUIRY
from test_api import client as client
from test_db import TEST_DATABASE_URL, _db_service, needs_db
from test_db import db as db

from cs_agent.domain import ReviewAction, TicketStatus
from cs_agent.schemas import InquiryIn, ReviewIn, SpecialistReplyIn, SpecialistRequestIn
from cs_agent.services.specialist_records import SpecialistConflict
from cs_agent.services.tickets import InvalidAction, TicketService


def request(**extra):
    return {
        "request_id": str(uuid4()),
        "to_dept": "CERT",
        "text": "Confirm the applicable standard.",
        "requested_by": "Reviewer",
        "channel": "email",
        "attachment_names": ["spec.pdf"],
        **extra,
    }


def reply(**extra):
    return {
        "reply_id": str(uuid4()),
        "text": "The required standard is IEC 60076.",
        "author": "Specialist",
        **extra,
    }


def test_request_reply_rewrite_approve_and_idempotency(client):
    tid = client.post("/api/tickets", json=INQUIRY).json()["ticket_id"]
    url = f"/api/tickets/{tid}"
    body = request()
    created = client.post(url + "/specialist-requests", json=body)
    assert created.status_code == 200
    assert created.json()["specialist_revision"] == 1
    assert created.json()["status"] == "READY_FOR_REVIEW"
    assert created.json()["specialist_requests"][0]["attachment_names"] == ["spec.pdf"]
    assert client.post(url + "/specialist-requests", json=body).json()["specialist_revision"] == 1
    assert (
        client.post(url + "/specialist-requests", json={**body, "text": "Changed"}).status_code
        == 409
    )
    assert (
        client.post(
            url + "/action", json={"action": "approve", "expected_specialist_revision": 1}
        ).status_code
        == 409
    )

    response = reply()
    reply_url = url + f"/specialist-requests/{body['request_id']}/reply"
    registered = client.post(reply_url, json=response)
    assert registered.status_code == 200
    assert registered.json()["specialist_revision"] == 2
    assert registered.json()["draft_specialist_revision"] == 0
    assert client.post(reply_url, json=response).json()["specialist_revision"] == 2
    assert client.post(reply_url, json=reply()).status_code == 409
    assert (
        client.post(
            url + "/action", json={"action": "approve", "expected_specialist_revision": 2}
        ).status_code
        == 409
    )
    service = client.app.state.tickets
    assert service._state(tid).next == ("review",)
    assert service._state(tid).values["specialist_replies"][0]["text"] == response["text"]
    rewritten = client.post(url + "/action", json={"action": "rewrite"})
    assert rewritten.status_code == 200
    assert rewritten.json()["draft_specialist_revision"] == 2
    sources = rewritten.json()["evidence"]
    assert any(e["doc_id"] == f"specialist:{response['reply_id']}" for e in sources)
    assert (
        client.post(
            url + "/action", json={"action": "approve", "expected_specialist_revision": 1}
        ).status_code
        == 409
    )
    approved = client.post(
        url + "/action", json={"action": "approve", "expected_specialist_revision": 2}
    )
    assert approved.json()["status"] == "APPROVED"
    assert client.post(url + "/specialist-requests", json=request()).status_code == 409


@pytest.mark.parametrize(
    "changes",
    [
        {"text": "  "},
        {"requested_by": ""},
        {"request_id": "oops"},
        {"text": "x" * 20001},
        {"attachment_names": [""]},
    ],
)
def test_request_validation(client, changes):
    tid = client.post("/api/tickets", json=INQUIRY).json()["ticket_id"]
    assert (
        client.post(f"/api/tickets/{tid}/specialist-requests", json=request(**changes)).status_code
        == 422
    )


def test_cross_ticket_ids_and_unknown_department(client):
    tid = client.post("/api/tickets", json=INQUIRY).json()["ticket_id"]
    other = client.post("/api/tickets", json=INQUIRY).json()["ticket_id"]
    body = request()
    url = f"/api/tickets/{tid}/specialist-requests"
    assert client.post(url, json=request(to_dept="UNLISTED")).status_code == 409
    assert client.post(url, json=body).status_code == 200
    assert client.post(f"/api/tickets/{other}/specialist-requests", json=body).status_code == 409
    assert (
        client.post(
            f"/api/tickets/{other}/specialist-requests/{body['request_id']}/reply", json=reply()
        ).status_code
        == 409
    )
    assert (
        client.post("/api/tickets/NOT-FOUND/specialist-requests", json=request()).status_code == 404
    )
    assert client.get(f"/api/tickets/{other}").json()["specialist_requests"] == []


def test_record_write_recovers_if_checkpoint_update_was_interrupted(client):
    service = client.app.state.tickets
    tid = client.post("/api/tickets", json=INQUIRY).json()["ticket_id"]
    body = SpecialistRequestIn(**request())
    service.records.add_specialist_request(tid, body)
    service.records.add_specialist_reply(tid, str(body.request_id), SpecialistReplyIn(**reply()))
    assert service._state(tid).values.get("specialist_revision", 0) == 0
    recreated = TicketService(service.graph, service.records)
    assert recreated.get(tid).specialist_revision == 2
    with pytest.raises(InvalidAction, match="재작성"):
        recreated.act(tid, ReviewIn(action=ReviewAction.APPROVE, expected_specialist_revision=2))
    assert recreated._state(tid).values["specialist_revision"] == 2
    assert recreated._state(tid).next == ("review",)


def test_pending_specialist_does_not_block_additional_info_request(client):
    service = client.app.state.tickets
    tid = client.post("/api/tickets", json=INQUIRY).json()["ticket_id"]
    service.add_specialist_request(tid, SpecialistRequestIn(**request()))
    prepared = service.act(
        tid, ReviewIn(action=ReviewAction.INFO_REQUEST, info_items=["serial_no"])
    )
    assert prepared.info_request
    sent = service.act(tid, ReviewIn(action=ReviewAction.APPROVE))
    assert sent.status == TicketStatus.WAITING_CUSTOMER
    original_reply = sent.final_reply
    pending = service.get(tid).specialist_requests[0]
    registered = service.add_specialist_reply(
        tid, str(pending.request_id), SpecialistReplyIn(**reply())
    )
    assert registered.status == TicketStatus.WAITING_CUSTOMER
    assert registered.final_reply == original_reply
    assert service._state(tid).next == ()
    resumed = service.reply(tid, InquiryIn(**{**INQUIRY, "body": "Serial number is 123456."}))
    assert resumed.specialist_revision == resumed.draft_specialist_revision == 2
    assert service._state(tid).next == ("review",)
    assert any(e.source == "specialist" for e in resumed.evidence)


def test_memory_lock_rejects_concurrent_mutation(client):
    service = client.app.state.tickets
    tid = client.post("/api/tickets", json=INQUIRY).json()["ticket_id"]
    with service.records.ticket_lock(tid), ThreadPoolExecutor(max_workers=1) as executor:
        result = executor.submit(
            service.add_specialist_request, tid, SpecialistRequestIn(**request())
        )
        with pytest.raises(InvalidAction, match="처리 중"):
            result.result()
    assert service.get(tid).specialist_requests == []


@needs_db
def test_sql_restart_and_lock_and_reply_recovery(db):
    from cs_agent.graph.builder import postgres_checkpointer
    from cs_agent.services.records import SqlRecords

    _, Session = db
    body = SpecialistRequestIn(**request())
    answer = SpecialistReplyIn(**reply())
    with postgres_checkpointer(TEST_DATABASE_URL) as saver:
        service = _db_service(Session, saver)
        tid = service.submit(InquiryIn(**INQUIRY)).ticket_id
        service.add_specialist_request(tid, body)
        # Durable reply committed, process stops before graph update.
        service.records.add_specialist_reply(tid, str(body.request_id), answer)
        with service.records.ticket_lock(tid):
            with pytest.raises(SpecialistConflict, match="처리 중"):
                with SqlRecords(Session).ticket_lock(tid):
                    pytest.fail("Second connection acquired the same lock")

    with postgres_checkpointer(TEST_DATABASE_URL) as saver:
        restored = _db_service(Session, saver)
        loaded = restored.get(tid)
        assert loaded.specialist_requests[0].reply.text == answer.text
        assert loaded.specialist_requests[0].attachment_names == ["spec.pdf"]
        assert loaded.specialist_revision == 2
        with pytest.raises(InvalidAction, match="재작성"):
            restored.act(tid, ReviewIn(action=ReviewAction.APPROVE, expected_specialist_revision=2))
        assert restored._state(tid).next == ("review",)
        rebuilt = restored.act(tid, ReviewIn(action=ReviewAction.REWRITE))
        assert rebuilt.draft_specialist_revision == 2
        assert (
            restored.act(
                tid, ReviewIn(action=ReviewAction.APPROVE, expected_specialist_revision=2)
            ).status
            == TicketStatus.APPROVED
        )


def test_multiple_departments_all_replies_are_required_and_grounded(client):
    service = client.app.state.tickets
    tid = service.submit(InquiryIn(**INQUIRY)).ticket_id
    first, second = (
        SpecialistRequestIn(**request()),
        SpecialistRequestIn(**request(to_dept="TS_TRF")),
    )
    service.add_specialist_request(tid, first)
    service.add_specialist_request(tid, second)
    reply_one = SpecialistReplyIn(**reply())
    reply_two = SpecialistReplyIn(**reply(text="The transformer dimensions are in drawing TR-009."))
    service.add_specialist_reply(tid, str(first.request_id), reply_one)
    partial = service.act(tid, ReviewIn(action=ReviewAction.REWRITE))
    assert partial.specialist_revision == 3
    with pytest.raises(InvalidAction, match="대기 중"):
        service.act(tid, ReviewIn(action=ReviewAction.APPROVE, expected_specialist_revision=3))
    service.add_specialist_reply(tid, str(second.request_id), reply_two)
    full = service.act(tid, ReviewIn(action=ReviewAction.REWRITE))
    assert full.draft_specialist_revision == full.specialist_revision == 4
    assert {e.doc_id for e in full.evidence if e.source == "specialist"} == {
        f"specialist:{reply_one.reply_id}",
        f"specialist:{reply_two.reply_id}",
    }
    assert (
        service.act(
            tid, ReviewIn(action=ReviewAction.APPROVE, expected_specialist_revision=4)
        ).status
        == TicketStatus.APPROVED
    )


def test_context_budget_rejects_new_request_before_storage(client):
    service = client.app.state.tickets
    tid = service.submit(InquiryIn(**INQUIRY)).ticket_id
    original = SpecialistRequestIn(**request(text="R" * 19500))
    service.add_specialist_request(tid, original)
    before = service.get(tid)
    with pytest.raises(InvalidAction, match="저장되지 않았습니다"):
        service.add_specialist_request(tid, SpecialistRequestIn(**request(text="S" * 19500)))
    assert service.get(tid) == before


def test_context_budget_rejects_reply_without_stranding_saved_context(client):
    service = client.app.state.tickets
    tid = service.submit(InquiryIn(**INQUIRY)).ticket_id
    original = SpecialistRequestIn(**request(text="R" * 20000))
    service.add_specialist_request(tid, original)
    before = service.get(tid)
    with pytest.raises(InvalidAction, match="줄여 다시 등록"):
        service.add_specialist_reply(
            tid, str(original.request_id), SpecialistReplyIn(**reply(text="A" * 20000))
        )
    assert service.get(tid) == before
    shorter = SpecialistReplyIn(**reply())
    service.add_specialist_reply(tid, str(original.request_id), shorter)
    assert service.get(tid).specialist_requests[0].reply.text == shorter.text


def test_idempotent_retries_do_not_recheck_new_context_budget(client, monkeypatch):
    from cs_agent.agents import drafting

    service = client.app.state.tickets
    tid = service.submit(InquiryIn(**INQUIRY)).ticket_id
    original = SpecialistRequestIn(**request())
    answer = SpecialistReplyIn(**reply())
    service.add_specialist_request(tid, original)
    service.add_specialist_reply(tid, str(original.request_id), answer)
    before = service.get(tid)
    monkeypatch.setattr(drafting, "MAX_SPECIALIST_CONTEXT_CHARS", 1)
    assert service.add_specialist_request(tid, original) == before
    assert service.add_specialist_reply(tid, str(original.request_id), answer) == before


def test_request_budget_reserves_space_for_a_concise_reply(client, monkeypatch):
    from cs_agent.agents import drafting

    service = client.app.state.tickets
    tid = service.submit(InquiryIn(**INQUIRY)).ticket_id
    monkeypatch.setattr(drafting, "MAX_SPECIALIST_CONTEXT_CHARS", 1200)
    original = SpecialistRequestIn(**request(text="R" * 176))
    service.add_specialist_request(tid, original)
    result = service.add_specialist_reply(
        tid, str(original.request_id), SpecialistReplyIn(**reply(text="A" * 512))
    )
    assert result.specialist_revision == 2
