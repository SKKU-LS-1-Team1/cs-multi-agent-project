import json
from dataclasses import replace

import pytest
from langgraph.types import Command

from cs_agent.agents import drafting as d
from cs_agent.config import Settings
from cs_agent.domain import Category, TicketStatus
from cs_agent.graph.builder import GraphDeps, build_ticket_graph
from cs_agent.llm.clients import Completion
from cs_agent.llm.router import LLMRouter
from cs_agent.rules.tables import load_tables
from cs_agent.schemas import Classification, Evidence, Extraction, InquiryIn, ReviewIn

MCCB = "MCCB-ABS-103c"
S100 = "INV-LSLV0075-S100"


class Writer:
    name = "writer-test"

    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.contexts = []

    def write(self, prompt):
        payload = prompt.split("# 입력 데이터\n", 1)[1].split("\n\n# 작성 요청", 1)[0]
        context = json.loads(payload)
        self.contexts.append(context)
        if self.error:
            raise self.error
        ref = context["allowed_citations"][0]
        text = self.response if self.response is not None else f"Requested guidance. [{ref}]"
        return Completion(text, self.name)


def router(writer, **settings):
    return LLMRouter(Settings(_env_file=None, **settings), writer=writer)


def extraction(category):
    code = {Category.DEFECT: S100, Category.FW_UPDATE: "ACB-AS-2000"}.get(category, MCCB)
    product = load_tables().products[code]
    return Extraction(
        product_code=code,
        product_family=product.family,
        language="en",
        error_code="E.OC" if category == Category.DEFECT else None,
        fw_version="1.3" if category == Category.FW_UPDATE else None,
        field_values={"quantity": "10", "incoterms": "FOB Busan", "required_date": "2026-11-30"},
    )


@pytest.mark.parametrize("category", list(Category))
def test_every_category_has_usable_template_and_one_writer_call(category):
    writer = Writer()
    result = d.write_draft(category, extraction(category), [], "Please advise.", router(writer))
    assert len(writer.contexts) == 1
    assert result.template == d.TEMPLATES[category].name
    assert result.model == writer.name
    assert all(result.slots.get(k) for k in d.required_slots(category))
    assert result.cited == [writer.contexts[0]["allowed_citations"][0]]


def test_quote_uses_decimal_and_does_not_round_quantity_to_moq():
    tables = load_tables()
    product = replace(tables.products[MCCB], list_price_usd="0.10")
    tables = replace(tables, products={**tables.products, MCCB: product})
    item = extraction(Category.QUOTE).model_copy(update={"field_values": {"quantity": "3"}})
    slots = d.build_slots(item, [], category=Category.QUOTE, tables=tables)
    assert (slots["unit_price_usd"], slots["quantity"], slots["total_usd"]) == ("0.10", "3", "0.30")
    assert slots["moq"] == "10"
    assert slots["quote_validity_days"] == "30"


@pytest.mark.parametrize("quantity", ["", "ten", "0", "-1", "1.5", "1,5", "10 kg", "5 or 10"])
def test_unconfirmed_or_invalid_quantity_stops_before_writer(quantity):
    writer = Writer()
    item = extraction(Category.QUOTE).model_copy(update={"field_values": {"quantity": quantity}})
    with pytest.raises(d.DraftingError, match="확인값"):
        d.write_draft(Category.QUOTE, item, [], "Quote please.", router(writer))
    assert writer.contexts == []


def test_quote_accepts_explicit_thousands_grouping():
    item = extraction(Category.QUOTE).model_copy(update={"field_values": {"quantity": "1,000 pcs"}})
    slots = d.build_slots(item, [], category=Category.QUOTE)
    assert (slots["quantity"], slots["total_usd"]) == ("1000", "85000.00")


def test_quote_validity_is_read_from_policy(tmp_path):
    settings = Settings(_env_file=None)
    path = tmp_path / "docs/policy/POL-ORDER.md"
    path.parent.mkdir(parents=True)
    policy = settings.raw_data_dir / "docs/policy/POL-ORDER.md"
    path.write_text(policy.read_text().replace("valid for 30 days", "valid for 45 days"))
    writer = Writer()
    draft = d.write_draft(
        Category.QUOTE,
        extraction(Category.QUOTE),
        [],
        "Quote.",
        router(writer, raw_data_dir=tmp_path),
    )
    assert draft.slots["quote_validity_days"] == "45"


def test_diagnosis_keeps_multiple_causes_for_same_error():
    writer = Writer()
    draft = d.write_draft(Category.DEFECT, extraction(Category.DEFECT), [], "E.OC", router(writer))
    faults = json.loads(draft.slots["fault_candidates"])
    assert {"FLT-001", "FLT-002"} <= {f["fault_id"] for f in faults}
    assert all(S100 in f["applies_to"].split(";") for f in faults)
    assert "확정 진단이 아닙니다" in writer.contexts[0]["categories"][0]["guide"]


def test_other_product_evidence_is_removed_and_cases_stay_separate():
    writer = Writer()
    evidence = [
        Evidence(source="docs", doc_id="DS-ACB-AS-2000", section="2.1", text="OTHER_PRODUCT_FACT"),
        Evidence(
            source="cases",
            doc_id="RC-EXAMPLE",
            text="PAST_CASE_ONLY",
            metadata={"product_code": MCCB},
        ),
    ]
    draft = d.write_draft(
        Category.TECH_SPEC, extraction(Category.TECH_SPEC), evidence, "Dimensions?", router(writer)
    )
    context = writer.contexts[0]
    assert "OTHER_PRODUCT_FACT" not in json.dumps(context["official_documents"])
    assert context["case_examples_not_current_facts"][0]["text"] == "PAST_CASE_ONLY"
    assert all("RC-EXAMPLE" not in ref for ref in draft.cited)


def test_citation_without_section_is_kept_when_explicitly_provided():
    writer = Writer()
    evidence = [Evidence(source="docs", doc_id="NOTICE", text="Official notice.")]
    draft = d.write_draft(
        Category.TECH_SPEC, extraction(Category.TECH_SPEC), evidence, "Specs?", router(writer)
    )
    assert draft.cited == ["NOTICE"]


def test_grouped_citations_are_all_preserved():
    writer = Writer(response="Lead time and validity [POL-ORDER#1, POL-ORDER#5].")
    draft = d.write_draft(Category.QUOTE, extraction(Category.QUOTE), [], "Quote?", router(writer))
    assert draft.cited == ["POL-ORDER#1", "POL-ORDER#5"]


def test_grouped_citation_cannot_hide_unknown_reference():
    writer = Writer(response="Details [POL-ORDER#1, INVENTED#9].")
    with pytest.raises(d.DraftingError, match="인용"):
        d.write_draft(Category.QUOTE, extraction(Category.QUOTE), [], "Quote?", router(writer))


def test_warranty_keeps_start_rule_and_only_target_product_period():
    writer = Writer()
    d.write_draft(Category.WARRANTY, extraction(Category.WARRANTY), [], "Warranty?", router(writer))
    policy = next(
        e["text"]
        for e in writer.contexts[0]["official_documents"]
        if e["reference"] == "POL-WARRANTY#1"
    )
    assert "18 months" in policy
    assert "6 months after shipment" in policy
    assert "ESS-PCS-100kW" not in policy
    assert "보증 승인" in writer.contexts[0]["categories"][0]["guide"]


def test_secondary_request_and_feedback_use_same_call():
    writer = Writer()
    draft = d.write_draft(
        Category.COMPLIANCE,
        extraction(Category.COMPLIANCE),
        [],
        "Certificate and quote please.",
        router(writer),
        secondary_category=Category.QUOTE,
        fix_notes=["통화 표시"],
        reviewer_feedback="더 짧게 작성",
    )
    assert len(writer.contexts) == 1
    context = writer.contexts[0]
    assert [c["category"] for c in context["categories"]] == ["COMPLIANCE", "QUOTE"]
    assert context["fix_notes"] == ["통화 표시"]
    assert context["reviewer_feedback"] == "더 짧게 작성"
    assert context["customer_language"] == "en"
    assert draft.slots["total_usd"] == "850.00"


@pytest.mark.parametrize(
    "writer",
    [
        Writer(response=""),
        Writer(error=TimeoutError()),
        Writer(response="Invented [DOES-NOT-EXIST#1]"),
    ],
)
def test_bad_model_output_or_error_is_not_successful_draft(writer):
    with pytest.raises(d.DraftingError):
        d.write_draft(
            Category.TECH_SPEC, extraction(Category.TECH_SPEC), [], "Specs?", router(writer)
        )


def test_missing_product_is_not_filled_from_nearest_document():
    writer = Writer()
    with pytest.raises(d.DraftingError, match="product_code"):
        d.write_draft(Category.MANUAL, Extraction(), [], "Manual?", router(writer))
    assert not writer.contexts


def test_graph_holds_missing_values_without_repeated_model_calls():
    writer = Writer()
    category = Category.QUOTE
    inquiry = InquiryIn(channel="email", body="Quote", category=category)
    item = extraction(category).model_copy(
        update={
            "field_values": {},
            "provided_info": ["product_model", "quantity", "incoterms"],
        }
    )
    deps = GraphDeps(
        llm=router(writer),
        classify=lambda *a: Classification(category=category),
        extract=lambda *a, **kw: item,
    )
    graph = build_ticket_graph(deps)
    config = {"configurable": {"thread_id": "missing-quote-values"}}
    graph.invoke({"ticket_id": "T-QUOTE", "inquiry": inquiry}, config)
    state = graph.get_state(config)
    assert state.values["status"] == TicketStatus.ON_HOLD
    assert state.next == ("review",)
    assert not writer.contexts
    assert state.values["draft"] is None
    assert state.values["checks"][0].passed is False

    # 초안이 없으면 승인으로 빈 답변을 확정할 수 없다.
    for review in (ReviewIn(action="approve"), ReviewIn(action="edit_approve", edited_text=" ")):
        graph.invoke(Command(resume=review.model_dump(mode="json")), config)
        state = graph.get_state(config)
        assert state.values["status"] == TicketStatus.ON_HOLD
        assert not state.values.get("final_reply")

    # 재작성 요청만으로 원천값이 생기지 않으며, 추가 고객 정보가 오면 다시 처리한다.
    graph.invoke(Command(resume=ReviewIn(action="rewrite").model_dump(mode="json")), config)
    assert graph.get_state(config).values["status"] == TicketStatus.ON_HOLD
    assert not writer.contexts
    item.field_values = {"quantity": "10"}
    graph.invoke(
        {"ticket_id": "T-QUOTE", "inquiry": inquiry.model_copy(update={"body": "Quantity: 10"})},
        config,
    )
    state = graph.get_state(config)
    assert state.values["status"] == TicketStatus.READY_FOR_REVIEW
    assert state.values["drafting_error"] is None
    assert len(writer.contexts) == 1


def test_graph_uses_actual_drafting_and_passes_secondary_request():
    writer = Writer()
    category = Category.COMPLIANCE
    item = extraction(category).model_copy(
        update={
            "provided_info": ["product_model", "target_standard", "target_country"],
        }
    )
    deps = GraphDeps(
        llm=router(writer),
        classify=lambda *a: Classification(category=category, secondary_category=Category.QUOTE),
        extract=lambda *a, **kw: item,
    )
    assert deps.write_draft is d.write_draft
    graph = build_ticket_graph(deps)
    config = {"configurable": {"thread_id": "composite-draft"}}
    graph.invoke(
        {
            "ticket_id": "T-COMPOSITE",
            "inquiry": InquiryIn(channel="email", body="Certificate and quote"),
        },
        config,
    )
    assert len(writer.contexts) == 1
    assert [c["category"] for c in writer.contexts[0]["categories"]] == ["COMPLIANCE", "QUOTE"]
    state = graph.get_state(config).values
    refs = {d._ref(e) for e in state["evidence"] if e.source == "docs"}
    assert set(writer.contexts[0]["allowed_citations"]) == refs
    assert set(state["draft"].cited) <= refs
