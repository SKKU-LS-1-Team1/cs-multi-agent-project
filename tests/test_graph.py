from langgraph.types import Command

from cs_agent.domain import ReviewAction, Route, TicketStatus
from cs_agent.graph.builder import build_ticket_graph
from cs_agent.schemas import InquiryIn, ReviewIn

SPEC = InquiryIn(
    customer_tier="GOLD",
    subject="Technical question",
    body="What is the vector group of TRF-OIL-1000? Application: substation.",
    provided_fields={"application": "substation"},
)


def _run(deps, inquiry, thread="t1"):
    graph = build_ticket_graph(deps)
    config = {"configurable": {"thread_id": thread}}
    graph.invoke({"ticket_id": thread, "inquiry": inquiry}, config)
    return graph, config


def test_simple_inquiry_reaches_review_with_draft(deps):
    graph, config = _run(deps, SPEC)
    state = graph.get_state(config)
    assert state.next == ("review",)  # 상담원 검토에서 멈춤
    values = state.values
    assert values["route"] == Route.DRAFT
    assert values["rules"].assigned_dept == "TS_TRF"
    assert values["evidence"][0].doc_id == "DS-TRF-OIL-1000"
    assert all(c.passed for c in values["checks"])

    graph.invoke(Command(resume=ReviewIn(action=ReviewAction.APPROVE).model_dump()), config)
    final = graph.get_state(config).values
    assert final["status"] == TicketStatus.APPROVED
    assert final["final_reply"] == values["draft"].text


def test_rewrite_request_goes_back_through_verify(deps):
    graph, config = _run(deps, SPEC)
    resume = ReviewIn(action=ReviewAction.REWRITE, feedback="더 짧게").model_dump()
    graph.invoke(Command(resume=resume), config)
    state = graph.get_state(config)
    assert state.next == ("review",)
    assert state.values["review_rounds"] == 1


def test_safety_goes_to_human_queue(deps):
    inquiry = InquiryIn(body="Smoke coming out of TRF-OIL-1000 after energizing!")
    graph, config = _run(deps, inquiry)
    values = graph.get_state(config).values
    assert values["route"] == Route.HUMAN
    assert values["status"] == TicketStatus.HUMAN_QUEUE
    assert values["draft"] is None


def test_missing_blocking_info_drafts_request(deps):
    inquiry = InquiryIn(body="Our S100 inverter keeps tripping, please help.")
    graph, config = _run(deps, inquiry)
    values = graph.get_state(config).values
    assert values["route"] == Route.INFO_REQUEST
    assert "serial number" in values["info_request"]
    graph.invoke(Command(resume=ReviewIn(action=ReviewAction.APPROVE).model_dump()), config)
    assert graph.get_state(config).values["status"] == TicketStatus.WAITING_CUSTOMER
