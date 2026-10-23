"""Customer history must reach analysis as ordered originals, never a merged latest turn."""

import stubs

from cs_agent.agents import analysis
from cs_agent.config import Settings
from cs_agent.domain import Category
from cs_agent.graph.builder import GraphDeps, build_ticket_graph
from cs_agent.llm.router import LLMRouter
from cs_agent.schemas import CheckResult, Draft, InquiryIn, ReviewIn
from cs_agent.services.tickets import TicketService


def test_reply_analysis_receives_latest_body_history_and_current_form_separately(monkeypatch):
    classified, extracted = [], []

    def classify(inquiry, llm, **kwargs):
        classified.append((inquiry, kwargs))
        return stubs.classify(inquiry, llm)

    def extract(inquiry, tables, *, llm=None, category=None, **kwargs):
        extracted.append((inquiry, kwargs))
        return stubs.extract(inquiry, tables, llm=llm, category=category)

    monkeypatch.setattr(analysis, "classify", classify)
    monkeypatch.setattr(analysis, "extract", extract)
    deps = GraphDeps(
        llm=LLMRouter(Settings(_env_file=None)),
        classify=classify,
        extract=extract,
        translate=lambda *args: None,
        first_pass=lambda *args: [],
        finalize_evidence=lambda *args, **kwargs: [],
        write_draft=lambda *args, **kwargs: Draft(text="Reply", model="stub"),
        write_info_request=lambda *args: "Please provide the missing information.",
        verify=lambda *args: [CheckResult(name="test", passed=True)],
    )
    service = TicketService(build_ticket_graph(deps))
    initial = InquiryIn(
        channel="email",
        customer_tier="GOLD",
        language="en",
        subject="Original product question",
        body="What are the dimensions of TRF-OIL-1000?",
        product_code="TRF-OIL-1000",
        category=Category.TECH_SPEC,
        provided_fields={"application": "substation", "serial_no": "OLD123"},
    )
    ticket = service.submit(initial)
    assert classified[-1][1]["category_is_current"] is True
    assert classified[-1][1]["transcript"] == []

    reply = initial.model_copy(
        update={
            "body": "Correction: please use the product and serial selected in my form.",
            "category": None,
            "product_code": "TRF-DRY-1000",
            "provided_fields": {"serial_no": "NEW456"},
        }
    )
    ticket = service.reply(ticket.ticket_id, reply)
    inquiry, options = classified[-1]
    assert inquiry.subject == initial.subject
    assert inquiry.body == reply.body
    assert [message.content for message in options["transcript"]] == [initial.body]
    assert options["category_is_current"] is False
    assert "[Customer reply" not in inquiry.body
    assert extracted[-1][1]["current_provided_fields"] == {"serial_no": "NEW456"}
    assert extracted[-1][1]["current_product_code"] == "TRF-DRY-1000"
    assert ticket.customer_revision == 1
    assert [message.body for message in ticket.customer_messages] == [initial.body, reply.body]

    latest = reply.model_copy(update={"category": Category.MANUAL, "body": "Send the manual."})
    service.reply(ticket.ticket_id, latest)
    inquiry, options = classified[-1]
    assert inquiry.category == Category.MANUAL
    assert options["category_is_current"] is True
    assert inquiry.body == latest.body
    assert [message.content for message in options["transcript"]] == [initial.body, reply.body]


def test_draft_is_bound_to_customer_revision():
    deps = GraphDeps(
        llm=LLMRouter(Settings(_env_file=None)),
        **stubs.ANALYSIS,
        translate=lambda *args: None,
        first_pass=lambda *args: [],
        finalize_evidence=lambda *args, **kwargs: [],
        write_draft=lambda *args, **kwargs: Draft(text="Reply", model="stub"),
        verify=lambda *args: [CheckResult(name="test", passed=True)],
    )
    service = TicketService(build_ticket_graph(deps))
    inquiry = InquiryIn(
        channel="email",
        customer_tier="GOLD",
        language="en",
        subject="Dimensions",
        body="Dimensions of TRF-OIL-1000?",
        product_code="TRF-OIL-1000",
        category=Category.TECH_SPEC,
        provided_fields={"application": "substation"},
    )
    ticket = service.submit(inquiry)
    assert ticket.draft is not None
    assert ticket.draft_customer_revision == 0
    ticket = service.reply(ticket.ticket_id, inquiry.model_copy(update={"body": "And weight?"}))
    assert ticket.draft is not None
    assert ticket.draft_customer_revision == ticket.customer_revision == 1

    requested = service.act(
        ticket.ticket_id, ReviewIn(action="info_request", info_items=["application"])
    )
    assert requested.info_request
    assert requested.draft is None  # the UI and approval must select the same candidate
    assert requested.draft_customer_revision == requested.customer_revision
    rewritten = service.act(ticket.ticket_id, ReviewIn(action="rewrite"))
    assert rewritten.info_request is None
    assert rewritten.draft.text == "Reply"
    approved = service.act(ticket.ticket_id, ReviewIn(action="approve"))
    assert approved.final_reply == rewritten.draft.text
