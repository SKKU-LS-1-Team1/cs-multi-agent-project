"""Progress notices preserve workflow, enforce customer isolation and require fresh approval."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from uuid import uuid4

import pytest
from stubs import pass_customer_qc
from test_api import INQUIRY
from test_api import client as client
from test_db import TEST_DATABASE_URL, _db_service, needs_db
from test_db import db as db

from cs_agent.agents.progress import ProgressError
from cs_agent.config import Settings
from cs_agent.llm.router import LLMRouter
from cs_agent.progress_schemas import ProgressApprovalIn, ProgressNoticeIn
from cs_agent.schemas import InquiryIn, ReviewIn
from cs_agent.services.progress import ProgressService
from cs_agent.services.tickets import InvalidAction


@pytest.fixture
def notices(client):
    service = client.app.state.progress
    generated, prepared = [], []

    def generate(facts, llm):
        generated.append(deepcopy(facts))
        return "\n".join(f"{f['ticket_id']}: Your response is awaiting review." for f in facts)

    def prepare(text, language, facts, llm):
        prepared.append((text, language, deepcopy(facts)))
        return f"Votre demande : {text}"

    service.generate = generate
    service.prepare = prepare
    return service, generated, prepared


def submit(client, **changes):
    response = client.post(
        "/api/tickets", json={**INQUIRY, "customer_id": "customer-1", "language": "fr", **changes}
    )
    assert response.status_code == 201
    return response.json()


def create(client, *tickets):
    anchor = tickets[0]["ticket_id"]
    body = {"notice_id": str(uuid4()), "ticket_ids": [t["ticket_id"] for t in tickets]}
    response = client.post(f"/api/tickets/{anchor}/progress-notices", json=body)
    return response, body


def approval_path(anchor, notice):
    return f"/api/tickets/{anchor}/progress-notices/{notice['notice_id']}/approve"


def test_notice_generation_and_preparation_do_not_dispatch_or_change_workflow(client, notices):
    service, generated, prepared = notices
    a, b = submit(client), submit(client)
    tid = a["ticket_id"]
    before = service.tickets._state(tid)
    response, body = create(client, a, b)
    assert response.status_code == 200
    notice = response.json()
    assert notice["status"] == "draft" and notice["final_text"] is None
    assert notice["target_language"] == "fr"
    assert len(generated) == 1 and len(generated[0]) == 2
    assert {k for f in generated[0] for k in f} == {
        "ticket_id",
        "status",
        "category",
        "product_code",
        "pending_specialist_count",
        "received_specialist_count",
        "waiting_for_customer",
        "resolution_outcome",
    }
    after = service.tickets._state(tid)
    assert after.next == before.next == ("review",)
    assert {k: v for k, v in after.values.items() if k != "progress_notices"} == before.values
    assert client.post(f"/api/tickets/{tid}/progress-notices", json=body).json() == notice
    assert len(generated) == 1

    exact = notice["draft_text"] + " Thank you for your patience."
    payload = {"edited_text": exact, "reviewer": "Staff"}
    response = client.post(approval_path(tid, notice), json=payload)
    assert response.status_code == 200
    approved = response.json()
    assert approved["status"] == "prepared"
    assert approved["approved_text"] == exact and approved["final_text"].startswith("Votre")
    assert approved["approved_at"] and approved["reviewer"] == "Staff"
    assert prepared[0][:2] == (exact, "fr")
    after = service.tickets._state(tid)
    assert after.next == before.next
    assert {k: v for k, v in after.values.items() if k != "progress_notices"} == before.values
    assert service.tickets.records.reviews[tid] == []
    assert client.get(f"/api/tickets/{tid}").json()["final_reply"] is None
    assert client.post(approval_path(tid, notice), json=payload).json() == approved
    assert len(prepared) == 1
    assert client.get(f"/api/tickets/{tid}/progress-notices").json() == [approved]
    assert (
        client.post(
            approval_path(tid, notice), json={**payload, "edited_text": "Changed."}
        ).status_code
        == 409
    )
    # Saving notice metadata must not consume the existing staff review interrupt.
    assert client.post(f"/api/tickets/{tid}/action", json={"action": "approve"}).status_code == 200


@pytest.mark.parametrize("changes", [{"customer_id": "different"}, {"language": "es"}])
def test_mixed_customer_or_language_rejected_without_model(client, notices, changes):
    _, generated, _ = notices
    a, b = submit(client), submit(client, **changes)
    response, _ = create(client, a, b)
    assert response.status_code == 409
    assert not generated
    assert client.get(f"/api/tickets/{a['ticket_id']}/progress-notices").json() == []


def test_missing_customer_invalid_selection_and_cross_ticket_isolation(client, notices):
    a, b = submit(client), submit(client, customer_id=None)
    assert create(client, b)[0].status_code == 409
    path = f"/api/tickets/{a['ticket_id']}/progress-notices"
    assert client.post(path, json={"notice_id": str(uuid4()), "ticket_ids": []}).status_code == 422
    assert (
        client.post(
            path,
            json={
                "notice_id": str(uuid4()),
                "ticket_ids": [a["ticket_id"], a["ticket_id"]],
            },
        ).status_code
        == 422
    )
    assert (
        client.post(
            path,
            json={
                "notice_id": str(uuid4()),
                "ticket_ids": [b["ticket_id"]],
            },
        ).status_code
        == 409
    )
    notice = create(client, a)[0].json()
    assert (
        client.post(
            approval_path(b["ticket_id"], notice),
            json={
                "edited_text": notice["draft_text"],
                "reviewer": "Staff",
            },
        ).status_code
        == 409
    )


def test_notice_identity_rejects_changed_selection_and_stale_customer_context(client, notices):
    service, generated, prepared = notices
    a, b = submit(client), submit(client)
    tid = a["ticket_id"]
    response, body = create(client, a)
    notice = response.json()
    path = f"/api/tickets/{tid}/progress-notices"
    assert client.post(path, json={**body, "ticket_ids": [tid, b["ticket_id"]]}).status_code == 409
    service.tickets.reply(
        tid,
        InquiryIn(
            **{
                **INQUIRY,
                "customer_id": "customer-1",
                "language": "fr",
                "body": "Updated information.",
            }
        ),
    )
    assert client.post(path, json=body).status_code == 409
    assert (
        client.post(
            approval_path(tid, notice),
            json={
                "edited_text": notice["draft_text"],
                "reviewer": "Staff",
            },
        ).status_code
        == 409
    )
    assert len(generated) == 1 and not prepared
    assert client.get(path).json() == [notice]


def test_generation_and_translation_failures_preserve_draft_and_allow_exact_retry(client, notices):
    service, generated, prepared = notices
    ticket = submit(client)
    tid = ticket["ticket_id"]
    generate, prepare = service.generate, service.prepare

    def fail(*args):
        raise ProgressError("Temporarily unavailable")

    service.generate = fail
    response, body = create(client, ticket)
    notice = response.json()
    assert notice["status"] == "draft" and notice["draft_text"] is None and notice["error"]
    service.generate = generate
    notice = client.post(f"/api/tickets/{tid}/progress-notices", json=body).json()
    assert notice["draft_text"] and notice["error"] is None and len(generated) == 1
    service.prepare = fail
    payload = {"edited_text": notice["draft_text"] + " Thank you.", "reviewer": "Staff"}
    failed = client.post(approval_path(tid, notice), json=payload).json()
    assert failed["status"] == "draft" and failed["approved_at"] is None
    assert failed["draft_text"] == notice["draft_text"]
    assert failed["approved_text"] == payload["edited_text"]
    assert failed["final_text"] is None and failed["error"]
    service.prepare = prepare
    done = client.post(approval_path(tid, notice), json=payload).json()
    assert done["status"] == "prepared" and done["error"] is None and len(prepared) == 1


def test_all_selected_ticket_locks_cover_model_and_snapshot_use(client, notices):
    service, _, _ = notices
    a, b = submit(client), submit(client)
    original_generate = service.generate

    def generate(facts, llm):
        with ThreadPoolExecutor(max_workers=1) as pool:
            mutation = pool.submit(service.tickets.reply, b["ticket_id"], InquiryIn(**INQUIRY))
            with pytest.raises(InvalidAction, match="처리 중"):
                mutation.result()
        return original_generate(facts, llm)

    service.generate = generate
    assert create(client, a, b)[0].status_code == 200
    assert service.tickets.get(b["ticket_id"]).customer_revision == 0


def test_closed_and_waiting_notice_saves_keep_graph_terminal(client, notices):
    service, _, _ = notices
    a = submit(client, language="en")
    tid = a["ticket_id"]
    service.tickets.act(tid, ReviewIn(action="approve"))
    before = service.tickets._state(tid)
    assert before.next == ()
    notice = create(client, a)[0].json()
    assert service.tickets._state(tid).next == ()
    service.tickets.resolve(tid)
    # The resolved status changed even without a new customer message.
    response = client.post(
        approval_path(tid, notice),
        json={
            "edited_text": notice["draft_text"],
            "reviewer": "Staff",
        },
    )
    assert response.status_code == 409
    resolved = create(client, a)[0].json()
    assert service.tickets._state(tid).next == ()
    service.tickets.reply(tid, InquiryIn(**INQUIRY))
    assert (
        client.post(
            approval_path(tid, resolved),
            json={
                "edited_text": resolved["draft_text"],
                "reviewer": "Staff",
            },
        ).status_code
        == 409
    )


def test_fake_model_cannot_create_usable_notice(client):
    ticket = submit(client)
    notice = create(client, ticket)[0].json()
    assert notice["status"] == "draft" and notice["draft_text"] is None and notice["error"]


def test_prepared_notice_retry_after_customer_correction_is_stale_but_history_survives(
    client, notices
):
    service, _, prepared = notices
    ticket = submit(client)
    tid = ticket["ticket_id"]
    notice = create(client, ticket)[0].json()
    payload = {"edited_text": notice["draft_text"], "reviewer": "Staff"}
    approved = client.post(approval_path(tid, notice), json=payload).json()
    service.tickets.reply(tid, InquiryIn(**{**INQUIRY, "body": "Please correct this request."}))
    assert client.post(approval_path(tid, notice), json=payload).status_code == 409
    assert client.get(f"/api/tickets/{tid}/progress-notices").json() == [approved]
    assert len(prepared) == 1


def test_waiting_customer_notice_preserves_sent_information_request(client, notices):
    service, _, _ = notices
    ticket = submit(client, language="en")
    tid = ticket["ticket_id"]
    service.tickets.act(tid, ReviewIn(action="info_request", info_items=["serial_no"]))
    sent = service.tickets.act(tid, ReviewIn(action="approve"))
    assert sent.status == "WAITING_CUSTOMER"
    before = service.tickets._state(tid)
    notice = create(client, ticket)[0].json()
    assert notice["source_facts"][0]["waiting_for_customer"] is True
    result = client.post(
        approval_path(tid, notice),
        json={
            "edited_text": notice["draft_text"],
            "reviewer": "Staff",
        },
    ).json()
    assert result["status"] == "prepared"
    after = service.tickets._state(tid)
    assert after.next == before.next == ()
    assert {k: v for k, v in after.values.items() if k != "progress_notices"} == before.values


def test_closed_escalation_with_previous_approval_error_stays_terminal(client, notices):
    service, _, _ = notices
    ticket = submit(client, language="en")
    tid = ticket["ticket_id"]
    service.tickets.graph.update_state(
        service.tickets._config(tid), {"approval_error": "Previous failed edit"}, as_node="ready"
    )
    service.tickets.act(tid, ReviewIn(action="escalate"))
    service.tickets.resolve(tid)
    before = service.tickets._state(tid)
    assert before.next == () and before.values["status"] == "RESOLVED"
    assert before.values["approval_error"]
    notice = create(client, ticket)[0].json()
    assert notice["draft_text"]
    after = service.tickets._state(tid)
    assert after.next == ()
    assert {k: v for k, v in after.values.items() if k != "progress_notices"} == before.values


@needs_db
def test_notice_checkpoint_survives_postgres_service_restart(db):
    from cs_agent.graph.builder import postgres_checkpointer

    _, Session = db
    with postgres_checkpointer(TEST_DATABASE_URL) as checkpointer:
        tickets = _db_service(Session, checkpointer)
        ticket = tickets.submit(InquiryIn(**{**INQUIRY, "customer_id": "customer-1"}))
        progress = ProgressService(
            tickets,
            LLMRouter(Settings(_env_file=None)),
            generate=lambda facts, llm: "English progress draft.",
            prepare=lambda text, language, facts, llm: text,
            check_customer_qc=pass_customer_qc,
        )
        notice = progress.create(
            ticket.ticket_id,
            ProgressNoticeIn(
                notice_id=uuid4(),
                ticket_ids=[ticket.ticket_id],
            ),
        )
        approved = progress.approve(
            ticket.ticket_id,
            str(notice.notice_id),
            ProgressApprovalIn(
                reviewer="Staff",
                edited_text=notice.draft_text,
            ),
        )
        before = tickets._state(ticket.ticket_id)
    with postgres_checkpointer(TEST_DATABASE_URL) as checkpointer:
        tickets = _db_service(Session, checkpointer)
        restored = ProgressService(tickets, LLMRouter(Settings(_env_file=None)))
        assert approved.status == "prepared"
        assert approved.customer_qc["decision"] == "PASS"
        assert restored.list(ticket.ticket_id) == [approved]
        assert tickets._state(ticket.ticket_id).next == before.next == ("review",)
        assert tickets.get(ticket.ticket_id).final_reply is None


@needs_db
def test_batch_sql_locks_use_one_connection_and_share_single_ticket_namespace(db):
    from sqlalchemy import event

    from cs_agent.services.records import SqlRecords
    from cs_agent.services.specialist_records import SpecialistConflict

    engine, Session = db
    records = SqlRecords(Session)
    checkouts = []

    def checkout(*args):
        checkouts.append(1)

    event.listen(engine, "checkout", checkout)
    try:
        with records.ticket_locks([f"T-{n}" for n in range(10)]):
            assert len(checkouts) == 1
            with pytest.raises(SpecialistConflict, match="처리 중"):
                with SqlRecords(Session).ticket_lock("T-5"):
                    pytest.fail("Single-ticket lock bypassed batch lock")
        # All locks are released, including any acquired before a batch conflict.
        with records.ticket_lock("T-5"):
            with pytest.raises(SpecialistConflict):
                with SqlRecords(Session).ticket_locks(["T-0", "T-5"]):
                    pytest.fail("Conflicting batch unexpectedly succeeded")
            with SqlRecords(Session).ticket_lock("T-0"):
                pass
    finally:
        event.remove(engine, "checkout", checkout)
