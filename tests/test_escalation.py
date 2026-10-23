"""CSA-55: 요청서 사실 보존, 모델 실패, API·검토 인터럽트·저장 회귀 검사."""

import json
from datetime import UTC, datetime, timedelta
from functools import partial

import pytest
from fastapi.testclient import TestClient
from stubs import ANALYSIS

from cs_agent.agents.escalation import (
    ESCALATION_ATTEMPTS,
    KST,
    EscalationError,
    InvalidEscalation,
    write_escalation_request,
)
from cs_agent.cache.store import MemoryKV
from cs_agent.config import Settings
from cs_agent.domain import Category, ReviewAction, TicketStatus
from cs_agent.graph.builder import GraphDeps, build_ticket_graph, serializer
from cs_agent.llm.clients import Completion
from cs_agent.llm.router import LLMRouter
from cs_agent.main import create_app
from cs_agent.rules.engine import apply_rules
from cs_agent.rules.tables import load_tables
from cs_agent.schemas import (
    CheckResult,
    Classification,
    Draft,
    EscalationRequest,
    Evidence,
    Extraction,
    InquiryIn,
    ReviewIn,
)
from cs_agent.services.tickets import InvalidAction, TicketService


class Writer:
    name = "test-writer"

    def __init__(self):
        self.prompts = []
        self.error = False
        self.queue = []  # 차례로 돌려줄 출력 (비면 self.output)
        self.output = {
            "summary": "고객이 대상 제품의 규격 확인을 요청했습니다.",
            "request": "적용 규격과 확인에 필요한 자료를 검토해 주세요.",
            "cited": [],
            "evidence_gap": "제공 문서에 해당 규격 설명이 없어 관련 규격 문서가 필요합니다.",
        }

    def write(self, prompt):
        self.prompts.append(prompt)
        if self.error:
            raise TimeoutError("provider timeout")
        out = self.queue.pop(0) if self.queue else self.output
        if isinstance(out, Exception):
            raise out
        return Completion(json.dumps(out, ensure_ascii=False), self.name)


def kst(moment):
    return moment.astimezone(KST).strftime("%Y-%m-%d %H:%M (KST)")


@pytest.fixture
def writer():
    return Writer()


@pytest.fixture
def llm(writer):
    return LLMRouter(Settings(_env_file=None, llm_provider="fake"), writer=writer, kv=MemoryKV())


@pytest.fixture
def state():
    inquiry = InquiryIn(
        channel="email",
        category=Category.TECH_SPEC,
        product_code="TRF-OIL-1000",
        body="Please confirm compliance.",
        language="en",
        country="France",
        customer_tier="GOLD",
        received_at=datetime(2026, 10, 21, tzinfo=UTC),
        provided_fields={"application": "substation", "serial_no": "WITHDRAWN-111"},
    )
    extraction = Extraction(
        product_code="TRF-OIL-1000",
        product_family="TRANSFORMER",
        field_values={
            "application": "substation",
            "target_standard": "IEC 60076",
            "photos": "[attachment: 6 photos]",
            "serial_no": "**MASKED**",
        },
        provided_info=["product_model", "application"],
        return_defect=False,
    )
    classification = Classification(category=Category.TECH_SPEC)
    return {
        "ticket_id": "T-TEST",
        "inquiry": inquiry,
        "extraction": extraction,
        "classification": classification,
        "rules": apply_rules(classification, extraction, inquiry.customer_tier, load_tables()),
        "draft": Draft(
            text="Please inspect the wiring. This is a suggestion, not a completed check."
        ),
        "evidence": [Evidence(source="docs", doc_id="DOC-A", section="2", text="Official text.")],
        "checks": [],
    }


@pytest.mark.parametrize(
    "dept,expected",
    [
        ("CERT", "target_standard"),
        ("QA_CLAIM", "return_defect"),
        ("FIELD_SVC", "preferred_visit_date"),
        ("RND_FW", "application"),
    ],
)
def test_department_fields_and_fixed_facts(state, llm, writer, dept, expected):
    writer.output["cited"] = ["DOC-A#2"]
    result = write_escalation_request(state, llm, dept)
    assert result.to_dept == dept
    assert expected in result.fields
    assert result.fields["product_code"] == "TRF-OIL-1000"
    assert result.fields["priority"] == state["rules"].priority
    expected_due = state["inquiry"].received_at + timedelta(hours=state["rules"].sla_resolution_h)
    assert result.fields["sla_due_at"] == expected_due.isoformat()
    for name in ("product_code", "priority"):
        assert result.fields[name] in result.text
    assert f"- SLA 마감: {kst(expected_due)}" in result.text  # 본문은 KST, fields 는 ISO
    assert result.fields["serial_no"] == "**MASKED**"
    assert result.fields["photos"] == "[attachment: 6 photos]"
    assert "WITHDRAWN-111" not in result.text
    assert result.fields["return_defect"] == "비불량 반품"
    assert result.cited == ["DOC-A#2"]
    assert result.model == "test-writer"
    if dept == "FIELD_SVC":
        assert result.fields["remote_check_results"] == "확인 필요"
        assert result.fields["preferred_visit_date"] == "확인 필요"
    assert "escalation_request" not in state  # 함수는 입력 상태를 바꾸지 않음


def test_default_department_and_conditional_reason(state, llm):
    result = write_escalation_request(state, llm)
    assert result.to_dept == state["rules"].escalate_to == "CERT"
    assert result.reason.startswith("이관 검토 기준:")
    assert "경우" in result.reason


@pytest.mark.parametrize("priority,hours", [("P1", 0.5), ("P2", 4), ("P3", 24), ("P4", 72)])
def test_protected_values_match_exactly_across_priorities(state, llm, priority, hours):
    state["rules"] = state["rules"].model_copy(
        update={"priority": priority, "sla_resolution_h": hours}
    )
    result = write_escalation_request(state, llm)
    assert result.fields["product_code"] == state["extraction"].product_code
    assert result.fields["priority"] == priority
    assert (
        result.fields["sla_due_at"]
        == (state["inquiry"].received_at + timedelta(hours=hours)).isoformat()
    )


def test_unknown_values_and_no_evidence_are_not_invented(state, llm):
    state.update(extraction=Extraction(), rules=None, evidence=[], draft=None)
    result = write_escalation_request(state, llm, "QA_CLAIM")
    assert result.fields["product_code"] == "확인 필요"
    assert result.fields["serial_no"] == "확인 필요"
    assert result.fields["return_defect"] == "확인 필요"
    assert result.fields["sla_due_at"] == "확인 필요"
    assert result.cited == []
    assert "확보된 인용 근거 없음" in result.text
    with pytest.raises(InvalidEscalation):
        write_escalation_request(state, llm)


@pytest.mark.parametrize("dept", ["", "NOT_A_DEPT", "somebody@example.com", "GCS_L1"])
def test_invalid_department_does_not_call_model(state, llm, writer, dept):
    with pytest.raises(InvalidEscalation):
        write_escalation_request(state, llm, dept)
    assert not writer.prompts


def test_context_uses_top_three_documents_not_cases(state, llm, writer):
    state["evidence"] = [
        Evidence(source="docs", doc_id=f"D{i}", section="1", text=f"Doc {i}", score=i)
        for i in range(5)
    ] + [Evidence(source="cases", doc_id="CASE", text="A past case", score=100)]
    write_escalation_request(state, llm)
    payload = json.loads(writer.prompts[-1].split("# INPUT DATA\n")[1])
    assert [d["id"] for d in payload["documents"]] == ["D4#1", "D3#1", "D2#1"]
    assert payload["draft"] == state["draft"].text


@pytest.mark.parametrize(
    "bad",
    [
        {"summary": "English only"},
        {"summary": "우선순위 P1입니다."},
        {"summary": "제품 TRF-OIL-1000입니다."},
        {"summary": "SLA는 100시간입니다."},
        {"cited": ["INVENTED#1"]},
        {"summary": ""},
        {"extra": "not allowed"},
    ],
)
def test_invalid_output_is_not_cached_as_success(state, llm, writer, bad):
    good = dict(writer.output)
    writer.output.update(bad)
    with pytest.raises(EscalationError, match="output_invalid"):
        write_escalation_request(state, llm)
    assert len(writer.prompts) == ESCALATION_ATTEMPTS  # 거절 사유를 붙여 다시 썼다
    writer.output = good
    assert write_escalation_request(state, llm).summary == good["summary"]
    assert len(writer.prompts) == ESCALATION_ATTEMPTS + 1


def test_provider_failure_is_explicit(state, llm, writer):
    writer.error = True
    with pytest.raises(EscalationError, match="generation_failed"):
        write_escalation_request(state, llm)


@pytest.mark.parametrize(
    "doc_id,section",
    [
        ("TG-PLC-XGI-CPUU", "3.2"),
        ("TG-MCCB-ABS-403c", "3.4"),
        ("RN-ACB-AS-2000", "3"),
    ],
)
def test_allowed_document_ids_containing_product_codes_are_not_rejected(
    state, llm, writer, doc_id, section
):
    """실제 평가에서 잘못 거절된 문서 ID 세 종류를 재현한다."""
    ref = f"{doc_id}#{section}"
    state["evidence"] = [Evidence(source="docs", doc_id=doc_id, section=section, text="공식 근거")]
    writer.output.update(
        request=f"공식 문서({ref})에 따른 검토를 요청합니다.", cited=[ref], evidence_gap=""
    )
    result = write_escalation_request(state, llm)
    assert result.cited == [ref]
    assert ref not in result.text
    assert "[근거 문서]" in result.text


def test_internal_request_displays_actual_document_and_section_names(state, llm, writer):
    state["evidence"] = [
        Evidence(source="docs", doc_id="POL-WARRANTY", section="4", text="Claim procedure.")
    ]
    writer.output.update(
        summary="고객이 보증 적용 여부를 문의했습니다.",
        request="[POL-WARRANTY#4]에 따라 접수 자료의 충분성을 검토해 주세요.",
        cited=["POL-WARRANTY#4"],
        evidence_gap="",
    )
    result = write_escalation_request(state, llm, "QA_CLAIM")
    name = "「Warranty and RMA Policy」의 ‘4. Claim procedure’"
    assert f"{name}에 따라" in result.text
    assert f"- {name}" in result.text
    assert "POL-WARRANTY" not in result.text
    assert result.cited == ["POL-WARRANTY#4"]
    assert "display_name" in writer.prompts[0]


def test_missing_document_title_is_not_invented(state, llm, writer):
    writer.output.update(
        summary="고객이 [DOC-A#2]의 내용을 문의했습니다.",
        cited=["DOC-A#2"],
        evidence_gap="",
    )
    result = write_escalation_request(state, llm)
    assert "참고 문서 1 (문서명 미확인)의 ‘2절 (절 제목 미확인)’" in result.summary
    assert "DOC-A#2" not in result.text
    assert result.cited == ["DOC-A#2"]


def test_source_titles_from_metadata_when_raw_document_is_absent(state, llm, writer):
    state["evidence"][0].metadata = {
        "document_title": "Installation Guide",
        "title": "2. Clearances",
    }
    writer.output.update(
        request="문서 DOC-A#2를 검토해 주세요. [attachment: 6 photos]도 확인 바랍니다.",
        cited=["DOC-A#2"],
        evidence_gap="",
    )
    result = write_escalation_request(state, llm)
    assert "「Installation Guide」의 ‘2. Clearances’" in result.text
    assert "[attachment: 6 photos]" in result.text
    assert "DOC-A#2" not in result.text


def test_explicit_inline_reference_is_retained_when_list_omits_it(state, llm, writer):
    ref = "TG-TRF-OIL-1000#3.4"
    state["evidence"] = [
        Evidence(source="docs", doc_id="TG-TRF-OIL-1000", section="3.4", text="가스켓 점검 절차")
    ]
    writer.output.update(
        request=f"[{ref}]에 설명된 점검의 필요성을 검토해 주세요.", cited=[], evidence_gap=""
    )
    assert write_escalation_request(state, llm).cited == [ref]


@pytest.mark.parametrize(
    "request_text",
    [
        "문서 TG-TRF-OIL-1000#3.4와 제품 TRF-OIL-1000을 확인해 주세요.",
        "문서 TG-TRF-OIL-1000#3.40에 따라 검토해 주세요.",
        "문서 TG-TRF-OIL-1000#3.4.1에 따라 검토해 주세요.",
        "문서 TG-TRF-OIL-1000#3.4-extra를 검토해 주세요.",
        "문서 POL-INVENTED#1을 검토해 주세요.",
        "문서 TG-TRF-OIL-1000#3.4를 참고하며 우선순위는 P1입니다.",
    ],
)
def test_reference_exemption_does_not_hide_unknown_refs_or_protected_values(
    state, llm, writer, request_text
):
    ref = "TG-TRF-OIL-1000#3.4"
    state["evidence"] = [
        Evidence(source="docs", doc_id="TG-TRF-OIL-1000", section="3.4", text="공식 근거")
    ]
    writer.output.update(request=request_text, cited=[ref], evidence_gap="")
    with pytest.raises(EscalationError, match="output_invalid"):
        write_escalation_request(state, llm)


def test_unrelated_document_is_not_attached_just_to_fill_citations(state, llm, writer):
    gap = (
        "제공된 문서는 고장 진단 절차이므로 설치 간격을 확인할 수 없습니다. 설치 지침이 필요합니다."
    )
    writer.output.update(cited=[], evidence_gap=gap)
    result = write_escalation_request(state, llm)
    assert result.cited == []
    assert gap in result.text
    assert "확인 필요" in result.text


def test_omitting_citations_and_reason_is_not_silent_success(state, llm, writer):
    writer.output.update(cited=[], evidence_gap="")
    with pytest.raises(EscalationError, match="output_invalid"):
        write_escalation_request(state, llm)


def test_mentioning_unrelated_reference_in_gap_does_not_count_as_citing_it(state, llm, writer):
    writer.output.update(cited=[], evidence_gap="DOC-A#2는 요청한 설치 간격과 무관합니다.")
    result = write_escalation_request(state, llm)
    assert result.cited == []
    assert "무관합니다" in result.text


def test_explicit_abstention_is_not_reversed_by_a_reference_in_summary(state, llm, writer):
    writer.output.update(
        summary="고객이 설치 간격을 질문했으나 DOC-A#2는 고장 진단을 다룹니다.",
        cited=[],
        evidence_gap="관련 설치 지침이 없어 확인 필요합니다.",
    )
    result = write_escalation_request(state, llm)
    assert result.cited == []
    assert "관련 설치 지침이 없어 확인 필요합니다." in result.text


def test_checkpoint_serializer_roundtrip(state, llm):
    request = write_escalation_request(state, llm)
    restored = serializer().loads_typed(serializer().dumps_typed(request))
    assert isinstance(restored, EscalationRequest)
    assert restored == request


@pytest.fixture
def client(llm):
    with TestClient(
        create_app(
            llm=llm,
            storage="memory",
            retrievers=(None, None),
            agents={
                **ANALYSIS,
                "write_draft": lambda *a, **k: Draft(text="Please review."),
                "verify": lambda *a, **k: [CheckResult(name="escalation_test", passed=True)],
                "translate": lambda *a: None,
            },
        )
    ) as client:
        yield client


def submit(client, state):
    response = client.post("/api/tickets", json=state["inquiry"].model_dump(mode="json"))
    assert response.status_code == 201
    return response.json()


def test_api_generate_get_and_approve_preserve_review(client, state, writer):
    original = submit(client, state)
    assert not writer.prompts  # 일반 접수에 요청서 호출 추가하지 않음
    tid = original["ticket_id"]
    generated = client.post(f"/api/tickets/{tid}/escalation-request")
    assert generated.status_code == 200, generated.text
    result = generated.json()
    assert result["status"] == original["status"] == "READY_FOR_REVIEW"
    assert result["assigned_dept"] == original["assigned_dept"]
    assert result["draft"] == original["draft"]
    assert result["escalation_request"]["to_dept"] == "CERT"
    assert client.get(f"/api/tickets/{tid}").json() == result
    service = client.app.state.tickets
    assert service._state(tid).next == ("review",)
    assert service.records.drafts[tid][-1]["kind"] == "escalation"
    saved = service.records.drafts[tid][-1]["slots"]
    assert EscalationRequest.model_validate(saved).model_dump() == result["escalation_request"]
    approved = client.post(f"/api/tickets/{tid}/action", json={"action": "approve"})
    assert approved.status_code == 200
    assert approved.json()["status"] == "APPROVED"
    assert approved.json()["final_reply"] == original["draft"]["text"]
    assert client.post(f"/api/tickets/{tid}/escalation-request").status_code == 409


def test_regenerate_failure_preserves_request_and_mismatch_cannot_transfer(client, state, writer):
    tid = submit(client, state)["ticket_id"]
    url = f"/api/tickets/{tid}/escalation-request"
    original = client.post(url).json()
    writer.error = True
    assert client.post(url, json={"to_dept": "FIELD_SVC"}).status_code == 503
    assert client.get(f"/api/tickets/{tid}").json() == original
    assert (
        client.post(
            f"/api/tickets/{tid}/action", json={"action": "escalate", "escalate_to": "FIELD_SVC"}
        ).status_code
        == 409
    )
    writer.error = False
    changed = client.post(url, json={"to_dept": "FIELD_SVC"})
    assert changed.status_code == 200
    assert changed.json()["escalation_request"]["to_dept"] == "FIELD_SVC"
    assert (
        client.post(
            f"/api/tickets/{tid}/action", json={"action": "escalate", "edited_text": " "}
        ).status_code
        == 409
    )
    sent = client.post(
        f"/api/tickets/{tid}/action",
        json={"action": "escalate", "edited_text": "담당자가 검토한 요청서"},
    )
    assert sent.status_code == 200, sent.text
    assert sent.json()["status"] == "ESCALATED"
    assert sent.json()["assigned_dept"] == "FIELD_SVC"
    assert sent.json()["escalation_request"]["text"] == "담당자가 검토한 요청서"


@pytest.mark.parametrize("action", ["rewrite", "info_request"])
def test_new_review_content_invalidates_request(client, state, action):
    tid = submit(client, state)["ticket_id"]
    assert client.post(f"/api/tickets/{tid}/escalation-request").status_code == 200
    response = client.post(f"/api/tickets/{tid}/action", json={"action": action})
    assert response.status_code == 200, response.text
    assert response.json()["escalation_request"] is None


def test_customer_reply_invalidates_request(client, state):
    tid = submit(client, state)["ticket_id"]
    client.post(f"/api/tickets/{tid}/escalation-request")
    service = client.app.state.tickets
    result = service.reply(tid, state["inquiry"].model_copy(update={"body": "Correction."}))
    assert result.escalation_request is None
    assert any(d["kind"] == "escalation" for d in service.records.drafts[tid])


def test_unknown_ticket_and_bad_department(client, state):
    assert client.post("/api/tickets/NO-SUCH/escalation-request").status_code == 404
    tid = submit(client, state)["ticket_id"]
    assert (
        client.post(
            f"/api/tickets/{tid}/escalation-request", json={"to_dept": "INVALID"}
        ).status_code
        == 409
    )


@pytest.mark.parametrize("wait_hours", [0, 5, 48])
def test_request_uses_ticket_sla_deadline(client, state, monkeypatch, writer, wait_hours):
    """서비스가 제공하는 마감을 필드·본문·모델 입력까지 동일하게 유지한다."""
    tid = submit(client, state)["ticket_id"]
    service = client.app.state.tickets
    original_get = service.get
    expected_due = original_get(tid).sla_due_at + timedelta(hours=wait_hours)

    def ticket_with_adjusted_deadline(ticket_id):
        return original_get(ticket_id).model_copy(update={"sla_due_at": expected_due})

    monkeypatch.setattr(service, "get", ticket_with_adjusted_deadline)
    response = client.post(f"/api/tickets/{tid}/escalation-request")
    assert response.status_code == 200, response.text
    result = response.json()
    request = result["escalation_request"]
    assert datetime.fromisoformat(request["fields"]["sla_due_at"]) == expected_due
    assert datetime.fromisoformat(result["sla_due_at"]) == expected_due
    assert kst(expected_due) in request["text"]
    payload = json.loads(writer.prompts[-1].split("# INPUT DATA\n")[1])
    assert payload["fixed_fields"]["sla_due_at"] == expected_due.isoformat()


def test_generation_cannot_overwrite_newer_ticket(client, state, llm):
    tid = submit(client, state)["ticket_id"]
    service = client.app.state.tickets

    def racing_writer(values, to_dept=None, **kwargs):
        result = write_escalation_request(values, llm, to_dept, **kwargs)
        service.act(tid, ReviewIn(action=ReviewAction.APPROVE))
        return result

    service.escalation_writer = racing_writer
    with pytest.raises(InvalidAction, match="문의가 변경"):
        service.generate_escalation_request(tid)
    assert service.get(tid).status == TicketStatus.APPROVED
    assert service.get(tid).escalation_request is None


def test_human_queue_generation_does_not_resume_processing(llm, state):
    deps = GraphDeps(llm=llm, **ANALYSIS, translate=lambda *a: None)
    service = TicketService(
        build_ticket_graph(deps), escalation_writer=partial(write_escalation_request, llm=llm)
    )
    inquiry = state["inquiry"].model_copy(update={"body": "Smoke and fire."})
    ticket = service.submit(inquiry)
    assert ticket.status == TicketStatus.HUMAN_QUEUE
    result = service.generate_escalation_request(ticket.ticket_id, "FIELD_SVC")
    assert result.status == TicketStatus.HUMAN_QUEUE
    assert service._state(ticket.ticket_id).next == ()


def test_hold_generation_preserves_review_and_can_transfer(llm, state):
    from cs_agent.agents.drafting import DraftingError

    def failed_draft(*a, **k):
        raise DraftingError("missing source")

    deps = GraphDeps(llm=llm, **ANALYSIS, translate=lambda *a: None, write_draft=failed_draft)
    service = TicketService(
        build_ticket_graph(deps), escalation_writer=partial(write_escalation_request, llm=llm)
    )
    ticket = service.submit(state["inquiry"])
    assert ticket.status == TicketStatus.ON_HOLD
    result = service.generate_escalation_request(ticket.ticket_id)
    assert result.status == TicketStatus.ON_HOLD
    assert service._state(ticket.ticket_id).next == ("review",)
    result = service.act(ticket.ticket_id, ReviewIn(action=ReviewAction.ESCALATE))
    assert result.status == TicketStatus.ESCALATED


def test_all_reference_escalation_departments_have_a_template(state, llm):
    tables = load_tables()
    targets = {row["escalation_dept"] for row in tables.routing.values() if row["escalation_dept"]}
    for target in targets:
        request = write_escalation_request(state, llm, target)
        assert request.to_dept == target
        assert request.fields["product_code"] == "TRF-OIL-1000"


def test_review_links_the_kind_the_operator_reviewed(client, state, monkeypatch):
    service = client.app.state.tickets
    kinds = []
    original = service.records.add_review

    def record(tid, review, *, draft_kind=None):
        kinds.append(draft_kind)
        return original(tid, review, draft_kind=draft_kind)

    monkeypatch.setattr(service.records, "add_review", record)
    for action in ("approve", "escalate"):
        tid = submit(client, state)["ticket_id"]
        client.post(f"/api/tickets/{tid}/escalation-request")
        response = client.post(f"/api/tickets/{tid}/action", json={"action": action})
        assert response.status_code == 200
    assert kinds == ["draft", "escalation"]


def test_rejected_output_is_retried_with_the_reason(state, llm, writer):
    """검사에 한 번 걸려도 거절 사유를 붙여 다시 쓰면 요청서가 나온다 (다시 누르지 않게)."""
    bad = {**writer.output, "summary": "우선순위 P1입니다."}
    writer.queue = [bad]

    result = write_escalation_request(state, llm)

    assert result.summary == writer.output["summary"]
    assert len(writer.prompts) == 2
    assert "# PREVIOUS OUTPUT REJECTED" not in writer.prompts[0]
    assert "# PREVIOUS OUTPUT REJECTED" in writer.prompts[1]
    assert "protected field repeated" in writer.prompts[1]


def test_provider_failure_is_retried(state, llm, writer):
    writer.queue = [TimeoutError("provider timeout")]

    assert write_escalation_request(state, llm).summary == writer.output["summary"]
    assert len(writer.prompts) == 2


def test_rate_limit_is_not_retried(state, llm, writer):
    from cs_agent.llm.router import RateLimited

    writer.queue = [RateLimited("gemini")]

    with pytest.raises(EscalationError, match="generation_failed"):
        write_escalation_request(state, llm)
    assert len(writer.prompts) == 1


def test_request_text_uses_korean_field_names_without_duplicate_product(state, llm, writer):
    state["extraction"] = state["extraction"].model_copy(
        update={
            "error_code": "E.OC",
            "field_values": {
                **state["extraction"].field_values,
                "product_model": "TRF-OIL-1000",
                "operating_condition": "during acceleration",
            },
        }
    )

    result = write_escalation_request(state, llm, "FIELD_SVC")

    assert "- 오류/증상: E.OC" in result.text
    assert "- 시리얼 번호: **MASKED**" in result.text
    assert "- 용도·사용 조건: substation" in result.text
    assert "product_model" not in result.fields  # 제품 코드와 같은 값은 한 번만
    assert not any(
        line.startswith(("- serial_no", "- application", "- product_model", "- error_code"))
        for line in result.text.splitlines()
    )
