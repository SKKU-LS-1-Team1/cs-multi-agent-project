import warnings

import pytest
from langgraph.types import Command

from cs_agent.config import Settings
from cs_agent.domain import Category, ReviewAction, Route, TicketStatus
from cs_agent.graph.builder import GraphDeps, build_ticket_graph
from cs_agent.llm.router import LLMRouter
from cs_agent.schemas import CheckResult, Draft, InquiryIn, ReviewIn

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

    def __init__(self, fail_checks: int = 0):
        self.fail_checks = fail_checks
        self.drafts: list[dict] = []
        self.info_requests: list[list[str]] = []

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
