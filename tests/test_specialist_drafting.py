"""CSA-62: 실제 작성·검증 경로, 모델 호출만 결정적인 응답으로 대체한다."""

import json

import pytest
from langgraph.types import Command

from cs_agent.agents import drafting, verification
from cs_agent.cache.store import MemoryKV
from cs_agent.config import Settings
from cs_agent.domain import Category, TicketStatus
from cs_agent.graph.builder import GraphDeps, build_ticket_graph
from cs_agent.llm.clients import Completion, Judgement
from cs_agent.llm.router import LLMRouter
from cs_agent.schemas import CheckResult, Classification, Draft, Extraction, InquiryIn

REPLY = {
    "request_id": "request-one",
    "to_dept": "Technical Support",
    "request_text": "Could the current voltage be 98765 V?",
    "reply_id": "reply-one",
    "text": "For this ticket, use the installation checklist before the next restart.",
    "author": "Engineer",
    "created_at": "2026-10-23T09:00:00Z",
}


class Writer:
    name = "specialist-test"

    def __init__(self, text=None):
        self.prompts = []
        self.text = text

    def write(self, prompt):
        self.prompts.append(prompt)
        context = payload(prompt)
        if self.text is not None:
            return Completion(self.text, self.name)
        if context.get("specialist_replies"):
            return Completion(
                "For MCCB-ABS-103c, please use the installation checklist before the next restart. "
                "[specialist:reply-one]",
                self.name,
            )
        return Completion(
            "For MCCB-ABS-103c, please refer to the installation documentation.", self.name
        )


class Judge:
    name = "specialist-judge"

    def __init__(self):
        self.prompts = []

    def judge(self, prompt, options):
        self.prompts.append(prompt)
        return Judgement("yes", 1.0, self.name)


def payload(prompt):
    return json.loads(prompt.split("# 입력 데이터\n", 1)[1].split("\n\n# 작성 요청", 1)[0])


def router(writer, judge=None):
    return LLMRouter(Settings(_env_file=None), writer=writer, gemini_judge=judge, kv=MemoryKV())


def extraction():
    return Extraction(
        product_code="MCCB-ABS-103c",
        product_family="LV_BREAKER",
        language="en",
        provided_info=["product_model", "doc_type", "preferred_language"],
    )


def test_reply_is_separate_source_with_request_only_as_unconfirmed_context():
    writer = Writer()
    result = drafting.write_draft(
        Category.MANUAL,
        extraction(),
        [],
        "Please advise.",
        router(writer),
        specialist_replies=[REPLY],
    )
    context = payload(writer.prompts[0])
    assert len(writer.prompts) == 1
    assert context["specialist_replies"][0]["reply"] == REPLY["text"]
    assert (
        context["specialist_replies"][0]["request_context_not_confirmed"] == REPLY["request_text"]
    )
    assert all(not e["reference"].startswith("specialist:") for e in context["official_documents"])
    assert "specialist:reply-one" in context["allowed_citations"]
    assert result.cited == ["specialist:reply-one"]
    assert "# ROLE" in writer.prompts[0] and "# SOURCE RULES" in writer.prompts[0]
    evidence = drafting.prepare_evidence(
        Category.MANUAL, extraction(), drafting.specialist_evidence([REPLY])
    )
    sources = verification.build_sources("Please advise.", evidence, result)
    assert "98765" not in sources.text  # 요청서의 가설이 숫자 검증을 통과시키지 않는다.
    assert not verification.check_specs(verification.extract_values("98765 V"), sources).passed
    assert REPLY["text"] in sources.text


def test_unknown_specialist_citation_is_rejected():
    writer = Writer("Please follow this advice. [specialist:invented]")
    with pytest.raises(drafting.DraftingError, match="제공되지 않은"):
        drafting.write_draft(
            Category.MANUAL,
            extraction(),
            [],
            "Please advise.",
            router(writer),
            specialist_replies=[REPLY],
        )


def test_specialist_reply_does_not_fill_missing_required_customer_input():
    writer = Writer()
    with pytest.raises(drafting.DraftingError, match="확인값이 부족"):
        drafting.write_draft(
            Category.QUOTE,
            extraction(),
            [],
            "Quote please.",
            router(writer),
            specialist_replies=[{**REPLY, "text": "The requested quantity may be 100 units."}],
        )
    assert writer.prompts == []


def test_graph_rewrite_passes_latest_reply_to_real_writer_and_verifier():
    writer, judge = Writer(), Judge()
    deps = GraphDeps(
        llm=router(writer, judge),
        translate=lambda *args: "문의",
        classify=lambda *args: Classification(category=Category.MANUAL),
        extract=lambda *args, **kwargs: extraction(),
    )
    graph = build_ticket_graph(deps)
    config = {"configurable": {"thread_id": "specialist-rewrite"}}
    graph.invoke(
        {
            "ticket_id": "T-REPLY",
            "inquiry": InquiryIn(
                channel="email", language="en", body="Please provide the installation manual."
            ),
        },
        config,
    )
    initial = graph.get_state(config).values
    assert initial["status"] == TicketStatus.READY_FOR_REVIEW, initial.get("checks")
    assert "specialist_replies" not in payload(writer.prompts[0])
    assert "Sources labelled specialist" not in judge.prompts[0]
    graph.update_state(config, {"specialist_replies": [REPLY], "specialist_revision": 1})
    graph.invoke(Command(resume={"action": "rewrite"}), config)
    updated = graph.get_state(config).values
    assert updated["status"] == TicketStatus.READY_FOR_REVIEW
    assert updated["draft"].cited == ["specialist:reply-one"]
    assert updated["draft_specialist_revision"] == 1
    assert all(c.passed for c in updated["checks"])
    assert len(writer.prompts) == 2  # 회신 재작성도 작성기 한 번, 재분류·재검색하지 않는다.
    assert "(specialist)" in judge.prompts[-1]
    assert REPLY["text"] in judge.prompts[-1]
    assert REPLY["request_text"] not in judge.prompts[-1]
    assert "cases describe past cases" in judge.prompts[-1]
    assert len([e for e in updated["evidence"] if e.source == "specialist"]) == 1


def test_existing_injected_writer_signature_is_unchanged():
    def old_writer(
        category, extraction, evidence, inquiry_text, llm, fix_notes=None, reviewer_feedback=None
    ):
        return Draft(text="A review draft.", template="manual", slots={"draft_language": "en"})

    graph = build_ticket_graph(
        GraphDeps(
            llm=router(Writer()),
            translate=lambda *args: "문의",
            classify=lambda *args: Classification(category=Category.MANUAL),
            extract=lambda *args, **kwargs: extraction(),
            write_draft=old_writer,
            verify=lambda *args: [CheckResult(name="stub", passed=True)],
        )
    )
    config = {"configurable": {"thread_id": "legacy-writer"}}
    graph.invoke(
        {
            "ticket_id": "T-OLD",
            "inquiry": InquiryIn(channel="email", body="Manual"),
            "specialist_replies": [REPLY],
            "specialist_revision": 2,
        },
        config,
    )
    assert graph.get_state(config).values["status"] == TicketStatus.READY_FOR_REVIEW


def test_long_reply_reaches_grounding_checker_without_losing_its_conclusion():
    reply = {**REPLY, "text": "Context. " * 400 + "Final finding: keep the equipment stopped."}
    evidence = drafting.specialist_evidence([reply])
    context = verification._context(
        "Please advise", evidence, Draft(text="Keep the equipment stopped.", template="manual")
    )
    assert "Final finding: keep the equipment stopped." in context


def test_translation_literals_preserve_specialist_citations():
    text = "Please check the cable. [specialist:reply-one]"
    assert "[specialist:reply-one]" in drafting._TRANSLATION_LITERALS.findall(text)


def test_excessive_specialist_context_holds_without_model_call():
    writer = Writer()
    graph = build_ticket_graph(
        GraphDeps(
            llm=router(writer),
            translate=lambda *args: "문의",
            classify=lambda *args: Classification(category=Category.MANUAL),
            extract=lambda *args, **kwargs: extraction(),
        )
    )
    config = {"configurable": {"thread_id": "oversize-specialist"}}
    graph.invoke(
        {
            "ticket_id": "T-LARGE",
            "inquiry": InquiryIn(channel="email", body="Manual please"),
            "specialist_replies": [{**REPLY, "text": "x" * 20_000, "request_text": "x" * 20_000}],
            "specialist_revision": 1,
        },
        config,
    )
    state = graph.get_state(config).values
    assert state["status"] == TicketStatus.ON_HOLD
    assert "40,000" in state["drafting_error"]
    assert state["draft"] is None
    assert not writer.prompts
    assert state["retries"] == 0
