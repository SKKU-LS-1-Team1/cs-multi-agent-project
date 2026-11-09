"""슬라이드의 세 예시를 비차단 권장 자료로 연결한다."""

import pytest
from test_analysis import ExtractorStub, JudgeStub

from cs_agent.agents.analysis import extract_details
from cs_agent.config import Settings
from cs_agent.domain import Category, Urgency
from cs_agent.rules.engine import apply_rules
from cs_agent.rules.investigation import investigation_info, recommended_fields
from cs_agent.rules.tables import load_tables
from cs_agent.schemas import Classification, Extraction, InquiryIn


@pytest.mark.parametrize(
    "family,text,code,expected",
    [
        (
            "DRIVE",
            "Overcurrent during acceleration",
            "E.OC",
            {
                "load_type",
                "motor_nameplate",
                "accel_decel_time",
                "cable_length",
                "carrier_frequency",
                "operating_condition",
                "logs",
            },
        ),
        (
            "PLC",
            "PLC communication failure",
            None,
            {
                "program_backup",
                "communication_config",
                "peer_device",
                "noise_environment",
                "occurrence_frequency",
            },
        ),
        (
            "LV_BREAKER",
            "차단기 오트립",
            None,
            {
                "current_waveform",
                "nearby_equipment_operation",
                "site_condition",
                "trip_settings_photo",
            },
        ),
    ],
)
def test_three_slide_examples_are_recommendations(family, text, code, expected):
    fields = recommended_fields(family, Category.DEFECT, text, code, load_tables())
    assert set(fields) == expected
    assert all(f in load_tables().request_labels for f in fields)


@pytest.mark.parametrize(
    "family,category,text,code",
    [
        ("HMI", Category.DEFECT, "Overcurrent", "E.OC"),
        ("DRIVE", Category.MANUAL, "Overcurrent manual", "E.OC"),
        ("DRIVE", Category.DEFECT, "Previously E.OC, now overheating", "E.OT"),
        (None, Category.DEFECT, "Overcurrent", "E.OC"),
    ],
)
def test_profiles_do_not_apply_to_other_products_or_document_requests(family, category, text, code):
    assert recommended_fields(family, category, text, code, load_tables()) == []


def test_received_and_withdrawn_values_are_distinguished_without_adding_blocking_fields():
    tables = load_tables()
    inquiry = InquiryIn(
        channel="email", body="E.OC during acceleration", product_code="INV-LSLV0750-iS7"
    )
    classification = Classification(category=Category.DEFECT)
    extraction = Extraction(
        product_code=inquiry.product_code,
        product_family="DRIVE",
        error_code="E.OC",
        field_values={"cable_length": "20 m", "carrier_frequency": "4 kHz"},
        unconfirmed_fields={"carrier_frequency": "withdrawn"},
    )
    state = {"inquiry": inquiry, "classification": classification, "extraction": extraction}
    result = investigation_info(state, tables)
    assert result["provided_fields"] == ["cable_length"]
    assert "carrier_frequency" in result["missing_fields"]
    rules = apply_rules(classification, extraction, "GOLD", tables)
    assert "cable_length" not in rules.required_info
    assert "carrier_frequency" not in rules.missing_blocking
    assert "current_waveform" not in rules.missing_blocking


def test_automatic_extraction_includes_recommended_fields_but_explicit_empty_list_is_respected():
    inquiry = InquiryIn(
        channel="email",
        category=Category.DEFECT,
        product_code="INV-LSLV0750-iS7",
        body="E.OC during acceleration; motor cable length is 20 m.",
    )
    extractor = ExtractorStub(
        {
            "fields": {"cable_length": {"value": "20 m", "evidence": "motor cable length is 20 m"}},
            "model": "gemini-test",
        }
    )
    result = extract_details(
        inquiry,
        load_tables(),
        llm=JudgeStub(),
        extractor=extractor,
        settings=Settings(_env_file=None, gemini_model_fast="gemini-test"),
    )
    assert result.fields["cable_length"] == "20 m"
    assert "cable_length" in extractor.calls[0]["input"]["requested_fields"]
    extractor.calls.clear()
    extract_details(
        inquiry,
        load_tables(),
        llm=JudgeStub(),
        extractor=extractor,
        requested_fields=[],
        settings=Settings(_env_file=None, gemini_model_fast="gemini-test"),
    )
    assert not extractor.calls


def referral_state():
    tables = load_tables()
    classification = Classification(category=Category.DEFECT)
    provided = {name: "provided" for name in tables.required[("DRIVE", "DEFECT")][0]}
    provided.update(serial_no="SN-42", error_code="E.OC", cable_length="20 m")
    extraction = Extraction(
        product_code="INV-LSLV0750-iS7",
        product_family="DRIVE",
        serial_no="SN-42",
        error_code="E.OC",
        field_values=provided,
        provided_info=list(provided),
    )
    return {
        "inquiry": InquiryIn(
            channel="web",
            body="Repeated overcurrent E.OC",
            category="DEFECT",
            product_code=extraction.product_code,
        ),
        "classification": classification,
        "extraction": extraction,
        "rules": apply_rules(classification, extraction, "STANDARD", tables),
        "escalation_advice": {"decision": "recommended", "to_dept": "FIELD_SVC"},
        "status": "READY_FOR_REVIEW",
    }


def test_referral_request_combines_missing_required_and_recommended_once():
    from cs_agent.rules.investigation import referral_request_fields

    state = referral_state()
    state["rules"].missing_info = ["photos", "logs"]
    state["extraction"].field_values.pop("logs")
    fields = referral_request_fields(state, load_tables())
    assert {"photos", "logs", "load_type", "accel_decel_time", "carrier_frequency"} <= set(fields)
    assert len(fields) == len(set(fields))
    assert "cable_length" not in fields
    assert "motor_nameplate" not in fields


@pytest.mark.parametrize("skip", ["unrelated", "already_referred", "urgent", "safety"])
def test_no_new_material_request_outside_normal_referral_preparation(skip):
    from cs_agent.rules.investigation import referral_request_fields

    state = referral_state()
    if skip == "unrelated":
        state["escalation_advice"] = {"decision": "not_needed"}
    elif skip == "already_referred":
        state["specialist_requests"] = [{"request_id": "R-1"}]
    elif skip == "urgent":
        state["rules"].priority = "P1"
    else:
        state["extraction"].urgency = Urgency.SAFETY
    assert referral_request_fields(state, load_tables()) == []


def test_unavailable_material_needs_evidence_and_is_not_re_requested():
    from cs_agent.agents import copilot
    from cs_agent.rules.investigation import referral_request_fields

    state = referral_state()
    ext = state["extraction"]
    ext.field_values.pop("logs")
    ext.unconfirmed_fields = {"logs": "UNAVAILABLE", "carrier_frequency": "UNAVAILABLE"}
    ext.unconfirmed_evidence = {"logs": "We cannot export the trip history."}
    state["rules"].missing_info = ["logs"]  # overlaps a required, non-blocking field
    fields = referral_request_fields(state, load_tables())
    assert "logs" not in fields
    assert "carrier_frequency" in fields  # unsupported claim must not hide a missing item
    plan = {r["field"]: r for r in copilot.request_plan(state, load_tables())}
    assert plan["logs"]["status"] == "unavailable"
    assert plan["logs"]["evidence"] == ext.unconfirmed_evidence["logs"]
    assert "logs" not in copilot.workflow(state, list(plan.values()))["request_fields"]
    state["rules"].missing_blocking = ["logs"]
    assert "logs" in referral_request_fields(state, load_tables())


@pytest.mark.parametrize(
    "urgency,decision,expected",
    [
        ("NONE", "recommended", "info_request"),
        ("NONE", "not_needed", "draft"),
        ("SITE_DOWN", "recommended", "draft"),
        ("SAFETY", "recommended", "human"),
    ],
)
def test_graph_requests_recommended_material_only_for_nonurgent_referral(
    urgency, decision, expected
):
    from test_graph import Calls

    from cs_agent.agents import copilot
    from cs_agent.graph.builder import GraphDeps, build_ticket_graph
    from cs_agent.llm.router import LLMRouter

    state = referral_state()
    state["extraction"].urgency = Urgency(urgency)
    calls = Calls()
    graph = build_ticket_graph(
        GraphDeps(
            llm=LLMRouter(Settings(_env_file=None, llm_provider="fake")),
            classify=lambda *a: state["classification"],
            extract=lambda *a, **kw: state["extraction"],
            assess_escalation=lambda *a: {"decision": decision, "to_dept": "FIELD_SVC"},
            write_info_request=calls.write_info_request,
            write_draft=calls.write_draft,
            verify=calls.verify,
        )
    )
    config = {"configurable": {"thread_id": "referral-materials"}}
    graph.invoke({"ticket_id": "T-MATERIALS", "inquiry": state["inquiry"]}, config)
    actual = graph.get_state(config).values
    assert actual["route"] == expected
    if expected == "info_request":
        assert set(calls.info_requests[0]) == {"load_type", "accel_decel_time", "carrier_frequency"}
        assert actual["info_request_fields"] == calls.info_requests[0]
        detail = copilot.view(actual, load_tables())
        assert detail["workflow"]["mode"] == "customer_request"
        assert detail["workflow"]["request_fields"] == calls.info_requests[0]
        assert actual["status"] == "READY_FOR_REVIEW"  # draft awaits staff, never auto-send
        assert not actual.get("final_reply")
    else:
        assert not calls.info_requests


@pytest.mark.parametrize("available", [True, False])
def test_collected_or_explicitly_unavailable_optional_material_needs_no_more_request(available):
    from cs_agent.agents import copilot
    from cs_agent.rules.investigation import referral_request_fields

    state = referral_state()
    for name in investigation_info(state)["missing_fields"]:
        if available:
            state["extraction"].field_values[name] = "provided"
        else:
            state["extraction"].unconfirmed_fields[name] = "UNAVAILABLE"
            state["extraction"].unconfirmed_evidence[name] = f"We cannot provide {name}."
    assert referral_request_fields(state, load_tables()) == []
    assert copilot.view(state, load_tables())["workflow"] == {
        "mode": "specialist_prepare",
        "next_action": "전문부서 이관 요청서·확보 자료 검토",
        "request_fields": [],
    }
