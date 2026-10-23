"""분석 근거·철회·대화 정정이 공통 출력으로 손실 없이 전달되는지 확인한다."""

import json
from types import SimpleNamespace

from cs_agent.agents import analysis
from cs_agent.config import Settings
from cs_agent.domain import Category, Urgency
from cs_agent.graph.builder import serializer
from cs_agent.schemas import Extraction, InquiryIn

S100 = "INV-LSLV0075-S100"
IS7 = "INV-LSLV0750-iS7"


class Router:
    settings = Settings(_env_file=None, llm_provider="fake", gemini_model_fast="gemini-test")

    def __init__(self, response=None, error=None):
        self.response = response or {"fields": {}, "model": "gemini-test"}
        self.error = error
        self.prompts = []

    def judge(self, task, prompt, options):
        self.prompts.append((task, json.loads(prompt)))
        answer = {"classify": "MANUAL", "extract_return_defect": "UNKNOWN"}.get(task, "NONE")
        return SimpleNamespace(answer=answer, confidence=0.95, model="jev-test")

    def extract_structured(self, task, prompt, schema, *, model):
        self.prompts.append((task, json.loads(prompt)))
        if self.error:
            raise self.error
        return self.response


def test_common_output_preserves_grounded_fields_and_original_values_independently():
    body = "Quantity: 10 units. S100. Error code: E.OC."
    router = Router(
        {
            "fields": {"quantity": {"value": "10", "evidence": "Quantity: 10 units."}},
            "model": "gemini-test",
        }
    )
    details = analysis.extract_details(
        InquiryIn(channel="email", body=body, provided_fields={"incoterms": "FOB Busan"}),
        llm=router,
        requested_fields=["quantity"],
        settings=router.settings,
    )
    common = details.to_extraction()
    assert common.field_values["quantity"] == "10"
    assert common.field_evidence["quantity"] == "Quantity: 10 units."
    assert common.field_sources["quantity"] == "model"
    assert common.field_sources["error_code"] == "rule"
    assert common.field_sources["incoterms"] == "customer"
    common.field_evidence["quantity"] = "Changed by consumer"
    assert details.evidence["quantity"] == "Quantity: 10 units."
    assert len([p for t, p in router.prompts if t == "extract_fields"]) == 1


def test_latest_product_correction_survives_handoff_with_previous_candidate():
    body = "S100으로 정정합니다."
    router = Router(
        {"fields": {"product_model": {"value": "S100", "evidence": body}}, "model": "gemini-test"}
    )
    inquiry = InquiryIn(
        channel="chat",
        subject="iS7 문의",
        body=body,
        product_code=IS7,
        provided_fields={"product_model": IS7},
    )
    common = analysis.extract(
        inquiry,
        llm=router,
        requested_fields=[],
        category=Category.MANUAL,
        transcript=[
            {"role": "user", "content": "제품은 iS7입니다."},
            {"role": "assistant", "content": "XGI 제품인가요?"},
        ],
    )
    assert common.product_code == S100
    assert common.field_evidence["product_model"] == body
    assert common.field_sources["product_model"] == "model"
    assert any(c["value"] == IS7 for c in common.field_candidates["product_model"])
    for _, prompt in router.prompts:
        assert prompt["customer_messages"] == ["제품은 iS7입니다."]
        assert prompt["body"] == body
    assert inquiry.product_code == IS7


def test_withdrawal_and_provider_failure_keep_reason_evidence_and_no_stale_value():
    body = "Ignore the previous serial number. Error code: E.OC."
    router = Router(error=TimeoutError("provider timeout"))
    common = analysis.extract(
        InquiryIn(
            channel="chat", body=body, product_code=S100, provided_fields={"serial_no": "OLD123"}
        ),
        llm=router,
        requested_fields=[],
        category=Category.DEFECT,
        transcript=[{"role": "user", "content": "S100. S/N OLD123."}],
    )
    assert common.serial_no is None
    assert "serial_no" not in common.provided_info and "serial_no" not in common.field_values
    assert "serial_no" not in common.field_evidence
    assert common.unconfirmed_fields["serial_no"] == "RETRACTED"
    assert common.unconfirmed_evidence["serial_no"] == body
    assert "structured_extraction_failed" in common.issues
    assert common.field_candidates["serial_no"][0]["value"] == "OLD123"
    assert common.error_code == "E.OC"
    restored = serializer().loads_typed(serializer().dumps_typed(common))
    assert restored == common


def test_safety_review_preserves_actual_judgement_without_changing_human_route():
    common = analysis.extract(
        InquiryIn(channel="email", body="S100. There is no smoke or fire."),
        llm=Router(),
        requested_fields=[],
        category=Category.DEFECT,
    )
    assert common.urgency == Urgency.SAFETY
    assert common.assessed_urgency == Urgency.NONE
    assert common.safety_review_required is True
    assert "safety_mention_requires_review" in common.issues


def test_legacy_common_extraction_defaults_do_not_invent_model_assessment():
    old = Extraction.model_validate({"product_code": S100, "urgency": "NONE"})
    assert old.field_evidence == {} and old.unconfirmed_fields == {}
    assert old.issues == [] and old.field_candidates == {}
    assert old.assessed_urgency is None
    assert old.safety_review_required is False


def test_past_selected_category_is_reclassified_but_current_selection_is_respected():
    router = Router()
    inquiry = InquiryIn(
        channel="chat",
        category=Category.QUOTE,
        body="Please cancel the quote request; I only need the installation manual.",
    )
    history = [{"role": "user", "content": "Please quote this product."}]
    classified = analysis.classify(inquiry, router, transcript=history, include_secondary=False)
    assert classified.category == Category.MANUAL
    assert router.prompts[0][1]["previous_category"] == "QUOTE"
    selected = analysis.classify(
        inquiry.model_copy(update={"category": Category.MANUAL}),
        router,
        transcript=history,
        category_is_current=True,
        include_secondary=False,
    )
    assert selected.category == Category.MANUAL and selected.model == "customer"
    assert len(router.prompts) == 1


def test_latest_form_serial_and_product_are_not_invalidated_by_old_narrative():
    router = Router()
    common = analysis.extract(
        InquiryIn(
            channel="chat",
            subject="iS7 문의",
            body="Updated the form fields.",
            product_code=IS7,
            provided_fields={"serial_no": "OLD123"},
        ),
        llm=router,
        requested_fields=[],
        category=Category.MANUAL,
        transcript=[{"role": "user", "content": "iS7. S/N OLD123."}],
        current_product_code=S100,
        current_provided_fields={"serial_no": "NEW456"},
    )
    assert common.product_code == S100 and common.serial_no == "NEW456"
    assert common.field_sources["product_model"] == "customer_form"
    assert common.field_sources["serial_no"] == "customer_form"
    assert common.field_evidence["serial_no"] == "NEW456"
    assert common.field_candidates["serial_no"][0]["value"] == "OLD123"
    field_calls = [p for task, p in router.prompts if task == "extract_fields"]
    assert len(field_calls) == 1
    assert field_calls[0]["confirmed_fields"]["serial_no"] == "NEW456"
    assert "serial_no" not in field_calls[0]["requested_fields"]
    assert "product_model" not in field_calls[0]["requested_fields"]


def test_latest_body_withdrawal_still_invalidates_same_turn_form_serial():
    body = "Ignore the serial number; I cannot verify it."
    router = Router()
    common = analysis.extract(
        InquiryIn(
            channel="chat", body=body, product_code=S100, provided_fields={"serial_no": "OLD123"}
        ),
        llm=router,
        requested_fields=[],
        category=Category.MANUAL,
        transcript=[{"role": "user", "content": "S100. S/N OLD123."}],
        current_provided_fields={"serial_no": "NEW456"},
    )
    assert common.serial_no is None and "serial_no" not in common.field_values
    assert common.unconfirmed_fields["serial_no"] == "RETRACTED"
    assert common.unconfirmed_evidence["serial_no"] == body
    assert any(
        c["value"] == "NEW456" and c["source"] == "customer_form"
        for c in common.field_candidates["serial_no"]
    )


def test_ambiguous_latest_form_product_does_not_restore_old_selected_product():
    common = analysis.extract(
        InquiryIn(channel="chat", body="See the form.", product_code=IS7),
        llm=Router(),
        requested_fields=[],
        category=Category.MANUAL,
        transcript=[{"role": "user", "content": "iS7"}],
        current_product_code="S100 or iS7",
    )
    assert common.product_code is None
    assert common.unconfirmed_fields["product_model"] == "UNKNOWN"
    assert "invalid_or_ambiguous_current_product" in common.issues


def test_latest_form_return_reason_is_current_in_judgement_payload():
    router = Router()
    latest = "We ordered the wrong model, not a defective unit."
    analysis.extract(
        InquiryIn(
            channel="chat",
            body="Updated the form.",
            category=Category.RETURN,
            product_code=S100,
            provided_fields={"return_reason": "The unit is defective."},
        ),
        llm=router,
        category=Category.RETURN,
        requested_fields=[],
        transcript=[{"role": "user", "content": "The unit is defective."}],
        current_provided_fields={"return_reason": latest},
    )
    prompts = [p for task, p in router.prompts if task == "extract_return_defect"]
    assert len(prompts) == 1
    assert prompts[0]["return_reason"] == latest
    assert prompts[0]["previous_return_reason"] is None
    assert prompts[0]["customer_messages"] == ["The unit is defective."]


def test_explicit_current_unknown_return_reason_is_not_replaced_by_previous_reason():
    router = Router()
    decision = analysis.extract_return_defect(
        InquiryIn(
            channel="chat",
            body="Updated the form.",
            provided_fields={"return_reason": "The unit is defective."},
        ),
        router,
        transcript=[{"role": "user", "content": "The unit is defective."}],
        current_return_reason="UNKNOWN",
    )
    assert router.prompts[0][1]["return_reason"] == "UNKNOWN"
    assert router.prompts[0][1]["previous_return_reason"] is None
    assert decision.return_defect is None
