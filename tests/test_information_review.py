"""Staff information review uses real customer history, rules and checkpoint persistence."""

import pytest
from test_api import INQUIRY
from test_api import client as client
from test_db import TEST_DATABASE_URL, _db_service, needs_db
from test_db import db as db

from cs_agent.schemas import InformationReviewIn, InquiryIn


def conversation(client):
    service = client.app.state.tickets
    ticket = service.submit(InquiryIn(**INQUIRY))
    return service.reply(
        ticket.ticket_id, InquiryIn(**{**INQUIRY, "body": "The application is a substation."})
    )


def review_body(ticket, fields=None):
    return {
        "reply_id": ticket.customer_messages[-1].message_id,
        "customer_revision": ticket.customer_revision,
        "reviewer": "담당자",
        "fields": fields
        or {
            "application": {
                "status": "confirmed",
                "value": "substation",
                "evidence": "고객 회신에서 설치 장소 확인",
            }
        },
    }


def test_history_and_get_expose_actual_analysis_without_calls(client, monkeypatch):
    ticket = conversation(client)
    service = client.app.state.tickets
    before = service._state(ticket.ticket_id).config

    def unexpected(*args, **kwargs):
        raise AssertionError("Read-only GET must not execute a model or graph")

    monkeypatch.setattr(service.graph, "invoke", unexpected)
    got = client.get(f"/api/tickets/{ticket.ticket_id}").json()
    assert len(got["customer_messages"]) == 2
    assert got["customer_messages"][0]["body"] == INQUIRY["body"]
    assert got["customer_messages"][1]["body"] == "The application is a substation."
    assert got["customer_messages"][1]["kind"] == "reply"
    assert got["customer_revision"] == 1
    assert got["classification"]["category"] == "TECH_SPEC"
    assert got["extraction"]["product_code"] == "TRF-OIL-1000"
    assert got["rules"]["required_info"]
    assert got["field_labels"]["application"]
    assert service._state(ticket.ticket_id).config == before


def test_confirmed_values_recalculate_rules_and_do_not_rerun_analysis(client, monkeypatch):
    ticket = conversation(client)
    service = client.app.state.tickets
    # Resuming from rules must not invoke the start/intake classification-extraction stages.
    before_followups = service._state(ticket.ticket_id).values["followups"]
    response = client.post(
        f"/api/tickets/{ticket.ticket_id}/information-review", json=review_body(ticket)
    )
    assert response.status_code == 200
    got = response.json()
    assert got["extraction"]["field_values"]["application"] == "substation"
    assert got["extraction"]["field_sources"]["application"] == "staff"
    assert got["extraction"]["field_evidence"]["application"] == "고객 회신에서 설치 장소 확인"
    assert "application" not in got["rules"]["missing_info"]
    assert len(got["information_reviews"]) == 1
    assert got["information_review"]["checked_at"]
    assert service._state(ticket.ticket_id).values["followups"] == before_followups

    def unexpected(*args, **kwargs):
        raise AssertionError("Identical retry must not regenerate")

    monkeypatch.setattr(service.graph, "invoke", unexpected)
    again = client.post(
        f"/api/tickets/{ticket.ticket_id}/information-review", json=review_body(ticket)
    )
    assert again.status_code == 200
    assert again.json()["information_review"] == got["information_review"]


def test_missing_product_removes_confirmed_identity_and_routes_to_info_request(client):
    ticket = conversation(client)
    body = review_body(
        ticket, {"product_model": {"status": "unusable", "evidence": "명판을 식별할 수 없음"}}
    )
    response = client.post(f"/api/tickets/{ticket.ticket_id}/information-review", json=body)
    assert response.status_code == 200
    got = response.json()
    assert got["extraction"]["product_code"] is None
    assert got["extraction"]["product_family"] is None
    assert "product_model" in got["rules"]["missing_blocking"]
    assert got["route"] == "info_request"
    assert got["extraction"]["unconfirmed_fields"]["product_model"] == "staff_unusable"


@pytest.mark.parametrize(
    "fields",
    [
        {"NOT_A_FIELD": {"status": "confirmed", "value": "x", "evidence": "e"}},
        {"serial_no": {"status": "confirmed", "evidence": "e"}},
        {"application": {"status": "confirmed", "value": "x", "evidence": ""}},
        {"product_model": {"status": "confirmed", "value": "not-a-model", "evidence": "e"}},
        {"application": {"status": "missing", "value": "contradiction", "evidence": "e"}},
    ],
)
def test_invalid_information_does_not_change_extraction(client, fields):
    ticket = conversation(client)
    response = client.post(
        f"/api/tickets/{ticket.ticket_id}/information-review", json=review_body(ticket, fields)
    )
    assert response.status_code == 409
    service = client.app.state.tickets
    assert service.get(ticket.ticket_id).extraction == ticket.extraction
    assert service.get(ticket.ticket_id).information_review is None


def test_new_customer_reply_invalidates_previous_review_and_stale_approval(client):
    old = conversation(client)
    service = client.app.state.tickets
    service.review_information(old.ticket_id, InformationReviewIn(**review_body(old)))
    newer = service.reply(
        old.ticket_id, InquiryIn(**{**INQUIRY, "body": "Correction: installed at a factory."})
    )
    assert newer.customer_revision == 2
    assert newer.information_review is None
    assert len(newer.information_reviews) == 1
    assert (
        client.post(
            f"/api/tickets/{old.ticket_id}/information-review", json=review_body(old)
        ).status_code
        == 409
    )
    assert (
        client.post(
            f"/api/tickets/{old.ticket_id}/action",
            json={"action": "approve", "expected_customer_revision": old.customer_revision},
        ).status_code
        == 409
    )


@needs_db
def test_customer_history_and_staff_review_restore_from_checkpoint(db):
    from cs_agent.graph.builder import postgres_checkpointer

    _, Session = db
    with postgres_checkpointer(TEST_DATABASE_URL) as saver:
        service = _db_service(Session, saver)
        initial = service.submit(InquiryIn(**INQUIRY))
        ticket = service.reply(
            initial.ticket_id, InquiryIn(**{**INQUIRY, "body": "Installed at a substation."})
        )
        reviewed = service.review_information(
            ticket.ticket_id, InformationReviewIn(**review_body(ticket))
        )
    with postgres_checkpointer(TEST_DATABASE_URL) as saver:
        restored = _db_service(Session, saver).get(initial.ticket_id)
        assert restored.customer_messages == reviewed.customer_messages
        assert restored.information_review == reviewed.information_review
        assert restored.extraction.field_sources["application"] == "staff"
        assert restored.rules.missing_info == reviewed.rules.missing_info


def test_stale_staff_review_and_stale_draft_timestamp_are_rejected(client):
    ticket = conversation(client)
    service = client.app.state.tickets
    first = service.review_information(ticket.ticket_id, InformationReviewIn(**review_body(ticket)))
    changed = review_body(
        ticket,
        {
            "application": {
                "status": "confirmed",
                "value": "factory",
                "evidence": "설치 장소 다시 확인",
            }
        },
    )
    response = client.post(f"/api/tickets/{ticket.ticket_id}/information-review", json=changed)
    assert response.status_code == 409
    changed["expected_reviewed_at"] = first.information_review.checked_at.isoformat()
    second = client.post(f"/api/tickets/{ticket.ticket_id}/information-review", json=changed)
    assert second.status_code == 200
    assert second.json()["extraction"]["field_values"]["application"] == "factory"
    rejected = client.post(
        f"/api/tickets/{ticket.ticket_id}/action",
        json={
            "action": "approve",
            "expected_customer_revision": ticket.customer_revision,
            "expected_information_reviewed_at": first.information_review.checked_at.isoformat(),
        },
    )
    assert rejected.status_code == 409
    assert len(service.get(ticket.ticket_id).information_reviews) == 2


def test_information_review_retry_resumes_failed_regeneration(client, monkeypatch):
    ticket = conversation(client)
    service = client.app.state.tickets
    original = service.graph.invoke
    calls = 0

    def fail_once(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("generation interrupted")
        return original(*args, **kwargs)

    monkeypatch.setattr(service.graph, "invoke", fail_once)
    body = InformationReviewIn(**review_body(ticket))
    with pytest.raises(RuntimeError, match="interrupted"):
        service.review_information(ticket.ticket_id, body)
    fixed = service.review_information(ticket.ticket_id, body)
    assert fixed.extraction.field_values["application"] == "substation"
    assert len(fixed.information_reviews) == 1
    assert calls == 2


def test_product_change_invalidates_old_unit_fields_until_explicit_reconfirmation():
    from cs_agent.rules.tables import load_tables
    from cs_agent.schemas import Extraction, InformationFieldReview
    from cs_agent.services.information import apply_information_review

    tables = load_tables()
    old = Extraction(
        product_code="TRF-OIL-1000",
        product_family="OIL_TRF",
        serial_no="OLD123",
        error_code="E01",
        fw_version="1.0",
        provided_info=["product_model", "serial_no", "current_fw", "error_code", "application"],
        field_values={
            "product_model": "TRF-OIL-1000",
            "application": "old site",
            "serial_no": "OLD123",
        },
    )
    changed, _ = apply_information_review(
        old,
        {
            "product_model": InformationFieldReview(
                status="confirmed", value="S100", evidence="새 명판 확인"
            )
        },
        tables,
    )
    assert changed.product_code == "INV-LSLV0075-S100"
    assert changed.serial_no is None and changed.error_code is None and changed.fw_version is None
    assert "application" not in changed.field_values
    assert changed.unconfirmed_fields["serial_no"] == "product_changed"
    assert old.serial_no == "OLD123"
    reconfirmed, _ = apply_information_review(
        old,
        {
            "serial_no": InformationFieldReview(
                status="confirmed", value="NEW456", evidence="새 시리얼 확인"
            ),
            "product_model": InformationFieldReview(
                status="confirmed", value="S100", evidence="새 명판 확인"
            ),
        },
        tables,
    )
    assert reconfirmed.serial_no == "NEW456"
    assert reconfirmed.field_sources["serial_no"] == "staff"


def test_staff_review_refreshes_retrieval_and_writer_without_reclassification():
    from stubs import ANALYSIS

    from cs_agent.config import Settings
    from cs_agent.graph.builder import GraphDeps, build_ticket_graph
    from cs_agent.llm.router import LLMRouter
    from cs_agent.schemas import CheckResult, Draft
    from cs_agent.services.tickets import TicketService

    calls = {"classify": 0, "extract": 0, "retrieve": [], "write": []}

    def classify(*args, **kwargs):
        calls["classify"] += 1
        return ANALYSIS["classify"](*args, **kwargs)

    def extract(*args, **kwargs):
        calls["extract"] += 1
        return ANALYSIS["extract"](*args, **kwargs)

    def retrieve(docs, cases, text):
        calls["retrieve"].append(text)
        return []

    def write(category, extraction, evidence, inquiry, llm, **kwargs):
        calls["write"].append(extraction.model_copy(deep=True))
        return Draft(text="Response", model="fake")

    graph = build_ticket_graph(
        GraphDeps(
            llm=LLMRouter(Settings(_env_file=None)),
            classify=classify,
            extract=extract,
            first_pass=retrieve,
            write_draft=write,
            verify=lambda *a: [CheckResult(name="stub", passed=True)],
        )
    )
    service = TicketService(graph)
    initial = service.submit(InquiryIn(**INQUIRY))
    ticket = service.reply(initial.ticket_id, InquiryIn(**{**INQUIRY, "body": "New details."}))
    assert calls["classify"] == calls["extract"] == 2
    before = len(calls["retrieve"])
    reviewed = service.review_information(
        ticket.ticket_id, InformationReviewIn(**review_body(ticket))
    )
    assert calls["classify"] == calls["extract"] == 2
    assert len(calls["retrieve"]) == before + 1
    assert "substation" in calls["retrieve"][-1]
    assert calls["write"][-1].field_values["application"] == "substation"
    assert reviewed.draft_information_reviewed_at == reviewed.information_review.checked_at
