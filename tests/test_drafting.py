import json
from dataclasses import replace

import pytest
from langgraph.types import Command

from cs_agent.agents import drafting as d
from cs_agent.agents import verification
from cs_agent.cache.store import MemoryKV
from cs_agent.config import Settings
from cs_agent.domain import Category, TicketStatus
from cs_agent.graph.builder import GraphDeps, build_ticket_graph
from cs_agent.llm.clients import Completion, Judgement
from cs_agent.llm.router import LLMRouter
from cs_agent.rules.tables import load_tables
from cs_agent.schemas import CheckResult, Classification, Evidence, Extraction, InquiryIn, ReviewIn

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
    assert result.text == "Requested guidance."


@pytest.mark.parametrize("language", ["fr", "ar", "zh", "en"])
def test_customer_language_is_preserved_while_review_draft_is_english(language):
    item = extraction(Category.MANUAL).model_copy(update={"language": language})
    writer = Writer()
    draft = d.write_draft(Category.MANUAL, item, [], "Manual please.", router(writer))
    assert draft.slots["draft_language"] == "en"
    assert writer.contexts[0]["draft_language"] == "en"
    assert writer.contexts[0]["customer_language"] == language
    assert item.language == language


class TranslationWriter:
    name = "translation-test"

    def __init__(self, text="", error=None):
        self.text, self.error = text, error
        self.calls = []

    def write(self, prompt):
        self.calls.append(prompt)
        if self.error:
            raise self.error
        return Completion(self.text, self.name)


@pytest.mark.parametrize(
    ("language", "target"),
    [
        (
            "ko",
            "S100에서 케이블과 모터를 1,000 V에서 절연 시험하십시오. 정격 7.5kW, 40 °C에서.",
        ),
        (
            "ja",
            "S100で、ケーブルとモーターを1,000 Vで絶縁試験してください。定格7.5kW、40 °Cで。",
        ),
    ],
)
def test_translation_with_particles_attached_to_units_and_codes_is_accepted(language, target):
    """한국어·일본어는 조사가 단위·코드에 바로 붙는다 ("1,000 V에서"). 맞는 번역을 막지 않는다"""
    source = (
        "On the S100, megger test the cable and motor at 1,000 V [TG-INV-LSLV0075-S100#3.2]. "
        "Rated 7.5kW, at 40 °C."
    )
    assert d.translate_reply(source, "en", language, router(TranslationWriter(target))) == target


def test_translation_preserves_numbers_and_codes_without_internal_citations():
    source = "S100 warranty: 24 months; price 260.00 USD [POL-WARRANTY#1]."
    target = "Garantie S100 : 24 mois ; prix 260.00 USD [POL-WARRANTY#1]."
    writer = TranslationWriter(target)
    assert d.translate_reply(source, "en", "fr", router(writer)) == (
        "Garantie S100 : 24 mois ; prix 260.00 USD."
    )
    assert json.loads(writer.calls[0].split("\n\n", 1)[1])["approved_reply"] == (
        "S100 warranty: 24 months; price 260.00 USD."
    )


@pytest.mark.parametrize(
    "target",
    [
        "Garantie S100 : 36 mois [POL-WARRANTY#1].",
        "Garantie S200 : 24 mois [POL-WARRANTY#1].",
        "Garantie S100 : 24 mois, 48 mois.",
        "Garantie S100.",
        "",
    ],
)
def test_invalid_translation_is_not_returned_as_final_reply(target):
    with pytest.raises(d.TranslationError):
        d.translate_reply(
            "S100 warranty: 24 months [POL-WARRANTY#1].",
            "en",
            "fr",
            router(TranslationWriter(target)),
        )


def test_english_customer_uses_exact_approved_text_without_model_call():
    writer = TranslationWriter(error=AssertionError("Must not call"))
    source = "Reviewed reply.\n"
    assert d.translate_reply(source, "en", "en-GB", router(writer)) == source
    assert not writer.calls


def test_customer_text_preserves_bracketed_content_and_separates_internal_sources():
    source = (
        "Warranty: 18 months [POL-WARRANTY#1, POL-WARRANTY#2].\n"
        "Check the unit [specialist:reply-one].\n"
        "See notice [NOTICE]. Keep [DS-100], [E.OC] and [attachment: 6 photos]."
    )
    assert d.customer_text(source, ["NOTICE"]) == (
        "Warranty: 18 months.\nCheck the unit.\n"
        "See notice. Keep [DS-100], [E.OC] and [attachment: 6 photos]."
    )


def test_english_customer_never_receives_internal_references():
    writer = TranslationWriter(error=AssertionError("Must not call"))
    assert (
        d.translate_reply(
            "Please check the unit [specialist:reply-one].", "en", "en", router(writer)
        )
        == "Please check the unit."
    )
    assert not writer.calls


def test_translation_api_error_is_reported_without_fallback_to_english():
    with pytest.raises(d.TranslationError, match="번역 호출"):
        d.translate_reply(
            "Approved reply", "en", "ar", router(TranslationWriter(error=TimeoutError()))
        )


def test_rejected_translation_cache_is_expired_and_success_is_reused():
    source = "The warranty for S100 is 24 months [POL-WARRANTY#1]."
    writer = TranslationWriter("La garantía de S100 es de 36 meses [POL-WARRANTY#1].")
    llm = LLMRouter(Settings(_env_file=None), writer=writer, kv=MemoryKV())
    with pytest.raises(d.TranslationError, match="수치"):
        d.translate_reply(source, "en", "es", llm)
    writer.text = "La garantía de S100 es de 24 meses [POL-WARRANTY#1]."
    assert d.translate_reply(source, "en", "es", llm) == "La garantía de S100 es de 24 meses."
    assert d.translate_reply(source, "en", "es", llm) == "La garantía de S100 es de 24 meses."
    assert len(writer.calls) == 2


def test_translation_in_wrong_language_is_rejected_even_when_numbers_match():
    with pytest.raises(d.TranslationError, match="언어"):
        d.translate_reply(
            "Please send a photograph of the product and the nameplate to our service team.",
            "en",
            "ar",
            router(
                TranslationWriter(
                    "Please provide a photo of the equipment and its nameplate "
                    "for our service team."
                )
            ),
        )


class GroundingJudge:
    name = "grounding-test"

    def __init__(self):
        self.calls = []

    def judge(self, prompt, options):
        self.calls.append(prompt)
        return Judgement("yes", 1.0, self.name)


@pytest.mark.parametrize("bad_price", [False, True])
def test_real_drafting_and_verification_connect_in_graph(bad_price):
    # 실제 작성기의 슬롯·프롬프트와 실제 CSA-31 검사를 함께 사용한다.
    # 외부 API 응답만 대역으로 고정해 값 검증과 재작성 분기를 재현한다.
    price = "999" if bad_price else "85"
    response = (
        f"For MCCB-ABS-103c, the unit price is {price} USD. For 10 units, the goods amount "
        "is 850.00 USD. The standard lead time is 4 weeks and the quotation validity is "
        "30 days [POL-ORDER#5]. Freight and taxes require separate confirmation."
    )
    writer, judge = Writer(response), GroundingJudge()
    llm = LLMRouter(Settings(_env_file=None), writer=writer, gemini_judge=judge, kv=MemoryKV())
    item = extraction(Category.QUOTE).model_copy(
        update={
            "provided_info": ["product_model", "quantity", "incoterms", "required_date"],
        }
    )
    deps = GraphDeps(
        llm=llm,
        classify=lambda *a: Classification(category=Category.QUOTE),
        extract=lambda *a, **kw: item,
    )
    assert deps.verify is verification.verify
    graph = build_ticket_graph(deps)
    config = {"configurable": {"thread_id": f"real-verifier-{bad_price}"}}
    graph.invoke(
        {
            "ticket_id": "T-VERIFY",
            "inquiry": InquiryIn(
                channel="email", language="es", body="Please quote 10 units of MCCB-ABS-103c."
            ),
        },
        config,
    )
    state = graph.get_state(config).values
    checks = {c.name: c for c in state["checks"]}
    assert checks["language"].passed  # 고객 언어는 es지만 검토 대상 초안은 en
    assert state["draft"].slots["draft_language"] == "en"
    assert state.get("final_reply") is None
    if bad_price:
        assert state["status"] == TicketStatus.ON_HOLD
        assert not checks["values"].passed
        assert state["retries"] == deps.max_retries
        assert not judge.calls  # 코드 검사 실패면 유료 근거 검증을 생략
    else:
        assert state["status"] == TicketStatus.READY_FOR_REVIEW, checks
        assert all(c.passed for c in checks.values())
        assert len(writer.contexts) == len(judge.calls) == 1


def test_secondary_policy_request_is_checked_before_paid_grounding():
    writer = Writer("Your return is approved.")
    judge = GroundingJudge()
    llm = LLMRouter(Settings(_env_file=None), writer=writer, gemini_judge=judge)
    item = extraction(Category.QUOTE).model_copy(
        update={
            "provided_info": ["product_model", "quantity", "incoterms", "required_date"],
        }
    )
    deps = GraphDeps(
        llm=llm,
        classify=lambda *a: Classification(
            category=Category.QUOTE, secondary_category=Category.RETURN
        ),
        extract=lambda *a, **kw: item,
    )
    graph = build_ticket_graph(deps)
    config = {"configurable": {"thread_id": "secondary-policy"}}
    graph.invoke(
        {
            "ticket_id": "T-SECONDARY",
            "inquiry": InquiryIn(
                channel="email",
                language="en",
                body="Quote 10 units and explain the return procedure.",
            ),
        },
        config,
    )
    state = graph.get_state(config).values
    assert state["status"] == TicketStatus.ON_HOLD
    assert state["checks"][0].name == "banned_secondary"
    assert not state["checks"][0].passed
    assert not judge.calls


def test_quote_uses_decimal_and_does_not_round_quantity_to_moq():
    tables = load_tables()
    product = replace(tables.products[MCCB], list_price_usd="0.10")
    tables = replace(tables, products={**tables.products, MCCB: product})
    item = extraction(Category.QUOTE).model_copy(update={"field_values": {"quantity": "3"}})
    slots = d.build_slots(item, [], category=Category.QUOTE, tables=tables)
    assert (slots["unit_price_usd"], slots["quantity"], slots["total_usd"]) == ("0.10", "3", "0.30")
    assert slots["moq"] == "10"
    assert slots["quote_validity_days"] == "30"


@pytest.mark.parametrize(
    "quantity",
    ["", "unknown", "0", "-1", "1.5", "1,5", "10 kg", "5 or 10", "1-3", "about 3", "3 boxes of 10"],
)
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


@pytest.mark.parametrize(
    ("raw", "quantity"),
    [
        ("one spare unit", "1"),
        ("una unidad", "1"),
        ("один комплект", "1"),
        ("bir adet", "1"),
        ("3 ชุด", "3"),
        ("10 ชุด", "10"),
        ("ten units", "10"),
        ("３台", "3"),
        ("٣ وحدات", "3"),
        ("2 unités", "2"),
        ("1 000 pcs", "1000"),
    ],
)
def test_quote_normalizes_only_confirmed_count_and_preserves_original(raw, quantity):
    item = extraction(Category.QUOTE).model_copy(update={"field_values": {"quantity": raw}})
    slots = d.build_slots(item, [], category=Category.QUOTE)
    assert slots["quantity"] == quantity
    assert slots["quantity_input"] == raw
    assert slots["total_usd"] == f"{int(quantity) * 85}.00"
    assert item.field_values["quantity"] == raw


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
    assert draft.text == "Lead time and validity."


def test_citations_alone_are_not_a_customer_answer():
    with pytest.raises(d.DraftingError, match="본문이 비어"):
        d.write_draft(
            Category.QUOTE,
            extraction(Category.QUOTE),
            [],
            "Quote?",
            router(Writer(response="[POL-ORDER#1]")),
        )


@pytest.mark.parametrize("separator", ["،", "؛", ",", ";", "、", "，"])
def test_localized_citation_separator_keeps_all_references_and_blocks_invention(separator):
    text = f"بيانات [POL-ORDER#1{separator} POL-ORDER#5]."
    draft = d.write_draft(
        Category.QUOTE, extraction(Category.QUOTE), [], "Quote?", router(Writer(response=text))
    )
    assert draft.cited == ["POL-ORDER#1", "POL-ORDER#5"]
    with pytest.raises(d.DraftingError, match="재작성"):
        d._citations(f"[POL-ORDER#1{separator} INVENTED#9]", ["POL-ORDER#1"])


def test_grouped_citation_cannot_hide_unknown_reference():
    writer = Writer(response="Details [POL-ORDER#1, INVENTED#9].")
    with pytest.raises(d.DraftingError, match="인용"):
        d.write_draft(Category.QUOTE, extraction(Category.QUOTE), [], "Quote?", router(writer))


def test_warranty_keeps_start_rule_and_only_target_product_period():
    writer = Writer()
    draft = d.write_draft(
        Category.WARRANTY, extraction(Category.WARRANTY), [], "Warranty?", router(writer)
    )
    assert draft.slots["warranty_months"] == "18"
    assert writer.contexts[0]["trusted_slots"]["warranty_months"] == "18"
    policy = next(
        e["text"]
        for e in writer.contexts[0]["official_documents"]
        if e["reference"] == "POL-WARRANTY#1"
    )
    assert "18 months" in policy
    assert "6 months after shipment" in policy
    assert "ESS-PCS-100kW" not in policy
    assert "보증 승인" in writer.contexts[0]["categories"][0]["guide"]


@pytest.mark.parametrize("period", ["", "0", "-1", "unknown"])
def test_missing_warranty_master_period_is_not_guessed_from_policy(period):
    tables = load_tables()
    product = replace(tables.products[MCCB], warranty_months=period)
    tables = replace(tables, products={**tables.products, MCCB: product})
    writer = Writer()
    with pytest.raises(d.DraftingError, match="warranty_months"):
        d.write_draft(
            Category.WARRANTY,
            extraction(Category.WARRANTY),
            [],
            "Warranty?",
            router(writer),
            tables=tables,
        )
    assert not writer.contexts


@pytest.mark.parametrize("category", [Category.DEFECT, Category.INSTALL, Category.FW_UPDATE])
def test_diagnostic_followup_has_official_service_escalation_reference(category):
    writer = Writer()
    d.write_draft(
        category, extraction(category), [], "Remote steps did not resolve it.", router(writer)
    )
    service = [
        item
        for item in writer.contexts[0]["official_documents"]
        if item["reference"].startswith("POL-SERVICE#")
    ]
    assert [item["reference"] for item in service] == ["POL-SERVICE#4"]
    assert "Field Service" in service[0]["text"]
    assert "Firmware R&D" in service[0]["text"]


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
        verify=lambda *a: [CheckResult(name="stub", passed=True)],
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
        verify=lambda *a: [CheckResult(name="stub", passed=True)],
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


@pytest.mark.parametrize(
    ("markdown", "plain"),
    [
        ("### E.OC causes\nText", "E.OC causes\nText"),
        ("1. **Load inertia:** too short [TG-INV-LSLV0075-S100#3.1].",
         "1. Load inertia: too short [TG-INV-LSLV0075-S100#3.1]."),
        ("*RMA note:* use the RMA number `F23`.", "RMA note: use the RMA number F23."),
        ("- __Event log__ (current)\n* item", "- Event log (current)\n* item"),
        ("2*3*4 and [POL-SERVICE#4]", "2*3*4 and [POL-SERVICE#4]"),
    ],
)  # fmt: skip
def test_plain_text_strips_markdown_but_keeps_citations_and_lists(markdown, plain):
    assert d.plain_text(markdown) == plain


def test_draft_is_plain_text_for_email_and_customer_screen():
    """실제 시연에서 고객 회신에 **·### 가 그대로 보였다. 규칙 + 출력에서 걷어 낸다."""
    writer = Writer(
        response="### Next steps\n1. **Megger test** at 1,000 V [TG-INV-LSLV0075-S100#3.2]."
    )
    item = extraction(Category.DEFECT)

    draft = d.write_draft(Category.DEFECT, item, [], "E.OC", router(writer))

    assert draft.text == "Next steps\n1. Megger test at 1,000 V."
    assert draft.cited == ["TG-INV-LSLV0075-S100#3.2"]
    assert "마크다운" in d.COMMON_INSTRUCTIONS
