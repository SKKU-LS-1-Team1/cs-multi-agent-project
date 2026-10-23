import warnings

import pytest
import stubs
from langgraph.types import Command

from cs_agent.agents import analysis
from cs_agent.agents.analysis import AnalysisError
from cs_agent.config import Settings
from cs_agent.domain import Category, ReviewAction, Route, TicketStatus
from cs_agent.graph import defaults
from cs_agent.graph.builder import GraphDeps, build_ticket_graph
from cs_agent.llm.router import LLMRouter
from cs_agent.schemas import CheckResult, Draft, InquiryIn, ReviewIn
from cs_agent.services.tickets import TicketService

SPEC_QUESTION = InquiryIn(
    channel="email",
    customer_tier="GOLD",
    language="en",
    subject="Dimensions of TRF-OIL-1000",
    body="What are the dimensions and weight of TRF-OIL-1000?",
    category=Category.TECH_SPEC,
    provided_fields={"application": "substation"},
)


class Calls:
    """에이전트 자리에 넣는 기록용 가짜 함수들"""

    def __init__(self, fail_checks: int = 0, analysis_down: int = 0):
        self.fail_checks = fail_checks
        self.analysis_down = analysis_down  # 앞에서부터 이 횟수만큼 분류 실패 (LLM 장애)
        self.drafts: list[dict] = []
        self.info_requests: list[list[str]] = []
        self.extract_categories: list = []

    def classify(self, inquiry, llm):
        if self.analysis_down:
            self.analysis_down -= 1
            raise AnalysisError("classification_failed")
        return stubs.classify(inquiry, llm)

    def extract(self, inquiry, tables, *, llm=None, category=None):
        self.extract_categories.append(category)
        return stubs.extract(inquiry, tables, llm=llm, category=category)

    def write_draft(self, category, extraction, evidence, text, llm, fix_notes=None,
                    reviewer_feedback=None):  # fmt: skip
        self.drafts.append({"fix_notes": fix_notes, "feedback": reviewer_feedback})
        return Draft(text=f"draft {len(self.drafts)}", model="stub")

    def verify(self, draft, category, slots, text, language, evidence, llm):
        if self.fail_checks:
            self.fail_checks -= 1
            return [CheckResult(name="values", passed=False, reason="정가 누락")]
        return [CheckResult(name="values", passed=True)]

    def write_info_request(self, missing, language, summary, llm):
        self.info_requests.append(missing)
        return f"please send {', '.join(missing)}"


@pytest.fixture
def run():
    def _run(inquiry: InquiryIn, calls: Calls | None = None, ticket_id: str = "T-1"):
        calls = calls or Calls()
        deps = GraphDeps(
            llm=LLMRouter(Settings(_env_file=None)),
            max_retries=2,
            classify=calls.classify,
            extract=calls.extract,
            write_draft=calls.write_draft,
            verify=calls.verify,
            write_info_request=calls.write_info_request,
        )
        graph = build_ticket_graph(deps)
        config = {"configurable": {"thread_id": ticket_id}}
        graph.invoke({"ticket_id": ticket_id, "inquiry": inquiry}, config)

        def resume(**review):
            graph.invoke(Command(resume=ReviewIn(**review).model_dump(mode="json")), config)
            return graph.get_state(config)

        return graph.get_state(config), resume, calls

    return _run


def test_simple_inquiry_reaches_review_then_approve(run):
    state, resume, calls = run(SPEC_QUESTION)

    assert state.next == ("review",)  # 상담원 버튼을 기다리며 멈춤
    v = state.values
    assert v["status"] == TicketStatus.READY_FOR_REVIEW
    assert v["route"] == Route.DRAFT
    assert (v["rules"].priority, v["rules"].assigned_dept) == ("P4", "TS_TRF")
    assert v["extraction"].product_code == "TRF-OIL-1000"

    done = resume(action=ReviewAction.APPROVE, reviewer="kim")

    assert done.next == ()
    assert done.values["status"] == TicketStatus.APPROVED
    assert done.values["final_reply"] == "draft 1"


@pytest.mark.parametrize("action", [ReviewAction.APPROVE, ReviewAction.EDIT_APPROVE])
def test_english_review_then_translate_approved_text_to_customer_language(action):
    translations, checked_languages = [], []

    def translate(text, source, target, llm):
        translations.append((text, source, target))
        return "Réponse validée."

    def verify(draft, category, slots, text, language, evidence, llm):
        checked_languages.append(language)
        return [CheckResult(name="language", passed=language == "en")]

    def extract(inquiry, tables, **kwargs):
        return stubs.extract(inquiry, tables, **kwargs).model_copy(update={"language": "en"})

    deps = GraphDeps(
        llm=LLMRouter(Settings(_env_file=None)),
        classify=stubs.classify,
        extract=extract,
        write_draft=lambda *a, **k: Draft(text="English draft.", slots={"draft_language": "en"}),
        verify=verify,
        translate_reply=translate,
    )
    service = TicketService(build_ticket_graph(deps))
    ticket = service.submit(SPEC_QUESTION.model_copy(update={"language": "fr"}))
    assert checked_languages == ["en"]
    assert not translations
    assert ticket.final_reply is None
    edited = "Edited English reply." if action == ReviewAction.EDIT_APPROVE else None
    result = service.act(ticket.ticket_id, ReviewIn(action=action, edited_text=edited))
    assert translations == [(edited or "English draft.", "en", "fr")]
    assert result.approved_reply == (edited or "English draft.")
    assert result.final_reply == "Réponse validée."
    assert result.final_reply_language == "fr"
    assert result.status == TicketStatus.APPROVED
    assert result.draft.text == "English draft."
    assert service.records.tickets[ticket.ticket_id]["language"] == "fr"


def test_translation_failure_retains_edited_reply_for_retry_and_reopen_clears_it():
    from cs_agent.agents.drafting import TranslationError

    translations = []

    def translate(text, source, target, llm):
        translations.append(text)
        if len(translations) == 1:
            raise TranslationError("Temporary translation failure")
        return "Réponse corrigée."

    deps = GraphDeps(
        llm=LLMRouter(Settings(_env_file=None)),
        classify=stubs.classify,
        extract=stubs.extract,
        write_draft=lambda *a, **k: Draft(text="Original draft.", slots={"draft_language": "en"}),
        verify=lambda *a: [CheckResult(name="translation_test", passed=True)],
        translate_reply=translate,
    )
    service = TicketService(build_ticket_graph(deps))
    inquiry = SPEC_QUESTION.model_copy(update={"language": "fr"})
    ticket = service.submit(inquiry)
    failed = service.act(
        ticket.ticket_id, ReviewIn(action="edit_approve", edited_text="Edited reply.")
    )
    assert failed.status == TicketStatus.ON_HOLD
    assert failed.approved_reply == "Edited reply."
    assert failed.final_reply is None and failed.translation_error
    assert service.graph.get_state(service._config(ticket.ticket_id)).next == ("review",)
    recovered = service.act(ticket.ticket_id, ReviewIn(action="approve"))
    assert translations == ["Edited reply.", "Edited reply."]
    assert recovered.status == TicketStatus.APPROVED
    assert recovered.final_reply == "Réponse corrigée."
    assert recovered.translation_error is None
    reopened = service.reply(ticket.ticket_id, inquiry)
    assert reopened.final_reply is None and reopened.approved_reply is None
    assert reopened.translation_error is None


@pytest.mark.parametrize("action", ["reject", "escalate"])
def test_nonapproval_does_not_translate(action):
    def forbidden(*args):
        raise AssertionError("No translation before approval")

    deps = GraphDeps(
        llm=LLMRouter(Settings(_env_file=None)),
        classify=stubs.classify,
        extract=stubs.extract,
        write_draft=lambda *a, **k: Draft(text="Draft", slots={"draft_language": "en"}),
        translate_reply=forbidden,
    )
    service = TicketService(build_ticket_graph(deps))
    ticket = service.submit(SPEC_QUESTION.model_copy(update={"language": "ar"}))
    result = service.act(ticket.ticket_id, ReviewIn(action=action, escalate_to="FIELD_SVC"))
    assert result.final_reply is None


def test_extracted_field_values_reach_draft_and_checkpoint():
    received = []

    def extract(inquiry, tables, *, llm=None, category=None):
        return stubs.extract(inquiry, tables).model_copy(
            update={"field_values": {"quantity": "10"}}
        )

    def write(category, extraction, evidence, text, llm, **kwargs):
        received.append(dict(extraction.field_values))
        return Draft(text="draft", slots=dict(extraction.field_values), model="stub")

    deps = GraphDeps(
        llm=LLMRouter(Settings(_env_file=None)),
        classify=stubs.classify,
        extract=extract,
        write_draft=write,
        verify=Calls().verify,
    )
    graph = build_ticket_graph(deps)
    config = {"configurable": {"thread_id": "field-values"}}
    graph.invoke({"ticket_id": "field-values", "inquiry": SPEC_QUESTION}, config)
    state = graph.get_state(config)
    assert received == [{"quantity": "10"}]
    assert state.values["extraction"].field_values == {"quantity": "10"}
    assert state.values["draft"].slots["quantity"] == "10"


def test_checkpoint_restores_our_models_without_warnings(run):
    with warnings.catch_warnings():
        warnings.simplefilter("error")  # 등록 안 된 타입이면 역직렬화 경고 → 실패
        state, resume, _ = run(SPEC_QUESTION)
        done = resume(action=ReviewAction.APPROVE)

    assert isinstance(done.values["inquiry"], InquiryIn)
    assert isinstance(done.values["review"], ReviewIn)


def test_failed_check_is_rewritten_with_fix_notes(run):
    state, _, calls = run(SPEC_QUESTION, Calls(fail_checks=1))

    assert state.values["status"] == TicketStatus.READY_FOR_REVIEW
    assert [d["fix_notes"] for d in calls.drafts] == [None, ["정가 누락"]]
    assert state.values["retries"] == 1


def test_too_many_failures_go_on_hold(run):
    state, resume, calls = run(SPEC_QUESTION, Calls(fail_checks=99))

    assert len(calls.drafts) == 3  # 처음 + 재작성 2회 (MAX_VERIFY_RETRIES)
    assert state.values["status"] == TicketStatus.ON_HOLD
    assert state.next == ("review",)
    assert resume(action=ReviewAction.REJECT).values["status"] == TicketStatus.REJECTED


def test_safety_goes_to_human_queue_without_draft(run):
    inquiry = SPEC_QUESTION.model_copy(update={"body": "TRF-OIL-1000 is emitting smoke!"})

    state, _, calls = run(inquiry)

    assert state.next == ()
    assert state.values["route"] == Route.HUMAN
    assert state.values["status"] == TicketStatus.HUMAN_QUEUE
    assert calls.drafts == []


def test_missing_product_asks_customer_first(run):
    inquiry = SPEC_QUESTION.model_copy(
        update={"subject": "Transformer dimensions", "body": "What are the dimensions?"}
    )

    state, resume, calls = run(inquiry)

    assert state.values["route"] == Route.INFO_REQUEST
    assert calls.info_requests == [["product_model"]]
    assert state.values["pending"] == "info_request"
    done = resume(action=ReviewAction.APPROVE)
    assert done.values["status"] == TicketStatus.WAITING_CUSTOMER  # SLA 정지
    assert done.values["final_reply"] == "please send product_model"


def test_info_request_is_localized_when_sent():
    """승인한 요청문(영어 틀 문장 등)은 보낼 때 고객 언어로 옮긴다. 상담원이 본 원문은 그대로."""
    calls = Calls()
    localized = []
    written_languages = []

    def write_request(missing, language, summary, llm):
        written_languages.append(language)
        return calls.write_info_request(missing, language, summary, llm)

    def localize(text, language, llm):
        localized.append((text, language))
        return f"[{language}] {text}"

    deps = GraphDeps(
        llm=LLMRouter(Settings(_env_file=None)),
        classify=calls.classify,
        extract=calls.extract,
        write_draft=calls.write_draft,
        verify=calls.verify,
        write_info_request=write_request,
        localize_info_request=localize,
    )
    graph = build_ticket_graph(deps)
    config = {"configurable": {"thread_id": "T-ES"}}
    inquiry = SPEC_QUESTION.model_copy(
        update={"subject": "Dimensiones", "body": "¿Cuáles son las dimensiones?", "language": "es"}
    )
    graph.invoke({"ticket_id": "T-ES", "inquiry": inquiry}, config)
    assert written_languages == ["en"]
    assert localized == []  # 고객 언어 변환은 담당자 확인 후에만 실행
    review = ReviewIn(action=ReviewAction.EDIT_APPROVE, edited_text="Please send the model.")
    graph.invoke(Command(resume=review.model_dump(mode="json")), config)

    v = graph.get_state(config).values
    assert localized == [("Please send the model.", "es")]
    assert v["final_reply"] == "[es] Please send the model."
    assert v["info_request"] == "please send product_model"  # 초안(상담원이 본 글)은 그대로


def test_info_request_held_when_translation_fails_then_sent_on_reapproval():
    """번역이 3번 다 실패하면 보내지 않고 보류, 상담원이 다시 승인하면 다시 번역해 보낸다."""
    from cs_agent.agents.info_request import LocalizationError

    calls = Calls()
    outcomes = [LocalizationError("es 번역 3번 실패"), "Por favor envíe el modelo."]

    def localize(text, language, llm):
        out = outcomes.pop(0)
        if isinstance(out, Exception):
            raise out
        return out

    deps = GraphDeps(
        llm=LLMRouter(Settings(_env_file=None)),
        classify=calls.classify,
        extract=calls.extract,
        write_draft=calls.write_draft,
        verify=calls.verify,
        write_info_request=calls.write_info_request,
        localize_info_request=localize,
    )
    graph = build_ticket_graph(deps)
    config = {"configurable": {"thread_id": "T-HOLD"}}
    inquiry = SPEC_QUESTION.model_copy(
        update={"subject": "Dimensiones", "body": "¿Cuáles son las dimensiones?", "language": "es"}
    )
    graph.invoke({"ticket_id": "T-HOLD", "inquiry": inquiry}, config)
    approve = Command(resume=ReviewIn(action=ReviewAction.APPROVE).model_dump(mode="json"))

    graph.invoke(approve, config)
    held = graph.get_state(config)
    assert held.values["status"] == TicketStatus.ON_HOLD
    assert held.values["final_reply"] is None  # 영어로 나가지 않았다
    assert held.values["approved_reply"] == "please send product_model"
    assert "3번 실패" in held.values["translation_error"]
    assert held.next == ("review",)  # 상담원 검토로 돌아왔다

    graph.invoke(approve, config)
    sent = graph.get_state(config).values
    assert sent["status"] == TicketStatus.WAITING_CUSTOMER
    assert sent["final_reply"] == "Por favor envíe el modelo."
    assert sent["translation_error"] is None


def test_held_info_request_keeps_reviewer_edit_on_reapproval():
    """수정 승인 → 번역 실패 보류 → 그냥 승인: 상담원이 고친 글을 번역한다 (초안으로 안 돌아감)."""
    from cs_agent.agents.info_request import LocalizationError

    calls = Calls()
    seen = []

    def localize(text, language, llm):
        seen.append(text)
        if len(seen) == 1:
            raise LocalizationError("번역 3번 실패")
        return f"[{language}] {text}"

    deps = GraphDeps(
        llm=LLMRouter(Settings(_env_file=None)),
        classify=calls.classify,
        extract=calls.extract,
        write_draft=calls.write_draft,
        verify=calls.verify,
        write_info_request=calls.write_info_request,
        localize_info_request=localize,
    )
    graph = build_ticket_graph(deps)
    config = {"configurable": {"thread_id": "T-EDIT"}}
    inquiry = SPEC_QUESTION.model_copy(
        update={"subject": "Dimensiones", "body": "¿Cuáles son las dimensiones?", "language": "es"}
    )
    graph.invoke({"ticket_id": "T-EDIT", "inquiry": inquiry}, config)
    edit = ReviewIn(action=ReviewAction.EDIT_APPROVE, edited_text="Please send model and photos.")
    graph.invoke(Command(resume=edit.model_dump(mode="json")), config)
    approve = ReviewIn(action=ReviewAction.APPROVE)
    graph.invoke(Command(resume=approve.model_dump(mode="json")), config)

    assert seen == ["Please send model and photos."] * 2
    assert graph.get_state(config).values["final_reply"] == "[es] Please send model and photos."


def test_reviewer_rewrite_then_edit_approve(run):
    _, resume, calls = run(SPEC_QUESTION)

    again = resume(action=ReviewAction.REWRITE, feedback="더 짧게")
    assert calls.drafts[-1]["feedback"] == "더 짧게"
    assert again.values["review_rounds"] == 1
    assert again.next == ("review",)

    done = resume(action=ReviewAction.EDIT_APPROVE, edited_text="고친 답변")
    assert done.values["final_reply"] == "고친 답변"


def test_reviewer_info_request_uses_checked_items(run):
    _, resume, calls = run(SPEC_QUESTION)

    state = resume(action=ReviewAction.INFO_REQUEST, info_items=["serial_no"])

    assert calls.info_requests == [["serial_no"]]
    assert state.values["pending"] == "info_request"
    assert state.next == ("review",)


def test_escalate(run):
    _, resume, _ = run(SPEC_QUESTION)

    done = resume(action=ReviewAction.ESCALATE, escalate_to="FIELD_SVC")

    assert done.values["status"] == TicketStatus.ESCALATED
    assert done.values["escalated_to"] == "FIELD_SVC"


# --- 분석 에이전트 연결 (CSA-26) ---------------------------------------------------------


def test_graph_uses_analysis_agent_not_placeholders():
    deps = GraphDeps(llm=LLMRouter(Settings(_env_file=None)))

    assert (deps.classify, deps.extract) == (analysis.classify, analysis.extract)
    assert not hasattr(defaults, "classify") and not hasattr(defaults, "extract")


def test_extract_receives_classified_category(run):
    _, _, calls = run(SPEC_QUESTION)

    assert calls.extract_categories == [Category.TECH_SPEC]


def test_offline_llm_never_fakes_analysis():
    """LLM 이 꺼져(fake) 있으면 분석 결과를 지어내지 않고 분석 대기로 멈춘다."""
    graph = build_ticket_graph(GraphDeps(llm=LLMRouter(Settings(_env_file=None))))
    config = {"configurable": {"thread_id": "T-OFF"}}

    graph.invoke({"ticket_id": "T-OFF", "inquiry": SPEC_QUESTION}, config)

    v = graph.get_state(config).values
    assert v["status"] == TicketStatus.ANALYSIS_PENDING
    assert v["analysis_error"]
    assert (v["classification"], v["rules"], v["route"], v.get("draft")) == (None, None, None, None)


def _service(calls: Calls) -> TicketService:
    deps = GraphDeps(
        llm=LLMRouter(Settings(_env_file=None)),
        classify=calls.classify,
        extract=calls.extract,
        write_draft=calls.write_draft,
        verify=calls.verify,
        write_info_request=calls.write_info_request,
    )
    return TicketService(build_ticket_graph(deps))


def test_analysis_outage_waits_then_retry_recovers():
    calls = Calls(analysis_down=1)
    service = _service(calls)

    pending = service.submit(SPEC_QUESTION)

    assert pending.status == TicketStatus.ANALYSIS_PENDING
    assert (pending.category, pending.route, pending.draft) == (None, None, None)
    assert calls.drafts == []
    assert service.work_list() == []  # 상담원 목록에는 아직 없다

    assert service.retry_pending() == [pending.ticket_id]

    ticket = service.get(pending.ticket_id)
    assert ticket.status == TicketStatus.READY_FOR_REVIEW
    assert ticket.category == Category.TECH_SPEC
    assert service.retry_pending() == []


def test_safety_goes_to_human_even_when_classification_fails():
    service = _service(Calls(analysis_down=1))
    smoke = SPEC_QUESTION.model_copy(update={"body": "TRF-OIL-1000 is emitting smoke!"})

    safety = service.submit(smoke)  # 분류 실패
    normal = service.submit(SPEC_QUESTION)

    assert safety.status == TicketStatus.HUMAN_QUEUE
    assert (safety.route, safety.category, safety.priority) == (Route.HUMAN, None, None)
    rows = service.work_list()
    assert [r["ticket_id"] for r in rows] == [safety.ticket_id, normal.ticket_id]
    assert rows[0]["at_risk"] is True  # 유형·부서·SLA 는 상담원이 정한다
    assert service.retry_pending() == []  # 사람 큐 건은 다시 돌리지 않는다


def test_escalated_ticket_moves_to_receiving_dept_in_work_list():
    service = _service(Calls())
    ticket = service.submit(SPEC_QUESTION)
    original = service.work_list()[0]["assigned_dept"]

    service.act(ticket.ticket_id, ReviewIn(action=ReviewAction.ESCALATE, escalate_to="FIELD_SVC"))

    assert [r["assigned_dept"] for r in service.work_list()] == ["FIELD_SVC"]
    assert [r["ticket_id"] for r in service.work_list(dept="FIELD_SVC")] == [ticket.ticket_id]
    assert service.work_list(dept=original) == []


def _waiting_scenario(service, monkeypatch):
    """0시 접수 → 2시 추가정보 요청 승인(대기 시작) → 12시 고객 회신(대기 10시간 끝)."""
    from datetime import UTC, datetime, timedelta

    from cs_agent.services import records

    t0 = datetime(2026, 10, 21, 0, 0, tzinfo=UTC)
    clock = {"now": t0}
    monkeypatch.setattr(records, "_now", lambda: clock["now"])
    at = lambda hours: t0 + timedelta(hours=hours)  # noqa: E731
    inquiry = SPEC_QUESTION.model_copy(
        update={
            "subject": "Transformer dimensions",
            "body": "What are the dimensions?",
            "received_at": t0,
        }
    )

    ticket = service.submit(inquiry)
    target_h = (service.get(ticket.ticket_id).sla_due_at - t0).total_seconds() / 3600
    clock["now"] = at(2)
    waiting = service.act(ticket.ticket_id, ReviewIn(action=ReviewAction.APPROVE))
    assert waiting.status == TicketStatus.WAITING_CUSTOMER
    return ticket.ticket_id, target_h, clock, at


def test_work_list_pauses_sla_while_waiting_for_customer(monkeypatch):
    service = _service(Calls())
    tid, target_h, clock, at = _waiting_scenario(service, monkeypatch)

    def ratio(hours):
        [row] = service.work_list(now=at(hours))
        return row["sla_ratio"]

    # 대기 중(2시~)에는 시계가 멈춘다: 12시에도 경과 2시간
    assert ratio(12) == ratio(2) == round(2 / target_h, 3)
    clock["now"] = at(12)
    reply = SPEC_QUESTION.model_copy(
        update={"body": "Model is TRF-OIL-1000.", "received_at": at(12)}
    )
    service.reply(tid, reply)  # 회신 → 대기 10시간이 쌓인다

    assert service.records.wait_hours(tid) == 10
    assert ratio(20) == round((20 - 10) / target_h, 3)
    [row] = service.work_list(now=at(20))
    assert row["sla_due_at"] == at(target_h + 10)
    assert service.get(tid).sla_due_at == at(target_h + 10)  # 상세 화면 마감도 같이 밀린다
