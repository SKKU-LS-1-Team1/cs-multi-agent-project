"""슬라이드의 세 예시를 비차단 권장 자료로 연결한다."""

import pytest
from test_analysis import ExtractorStub, JudgeStub

from cs_agent.agents.analysis import extract_details
from cs_agent.config import Settings
from cs_agent.domain import Category
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
