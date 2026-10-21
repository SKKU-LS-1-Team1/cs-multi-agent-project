import pytest

from cs_agent.chatbot.form_filler import InquiryDraftForm, fill_form
from cs_agent.config import Settings
from cs_agent.domain import Category
from cs_agent.llm.clients import Completion
from cs_agent.llm.router import LLMRouter
from cs_agent.rules.tables import load_tables
from cs_agent.schemas import Classification, Extraction

TABLES = load_tables()

# 챗봇 기록: 고객 / 챗봇 답변 순서로 번갈아 쌓인다 (api/chat.py)
S100_CHAT = [
    "S100 가속 중에 E.OC 가 떠요",
    "가속 시간(F23)을 늘려 보세요. 그래도 같으면 알려 주세요.",
    "가속 시간을 늘렸는데도 다시 E.OC 가 발생해요",
    "해결되지 않아 상담원에게 넘기겠습니다.",
]


class ScriptedWriter:
    name = "gemini-writer"

    def __init__(self, *outputs):
        self.outputs = list(outputs)
        self.prompts: list[str] = []

    def write(self, prompt):
        self.prompts.append(prompt)
        out = self.outputs.pop(0)
        if isinstance(out, Exception):
            raise out
        return Completion(out, self.name)


def live(writer) -> LLMRouter:
    return LLMRouter(Settings(_env_file=None, llm_provider="live"), writer=writer)


def _defect(**kw) -> tuple[Classification, Extraction]:
    extraction = Extraction(
        product_code="INV-LSLV0075-S100",
        product_family="DRIVE",
        error_code="E.OC",
        field_values={"operating_condition": "during acceleration"},
        **kw,
    )
    return Classification(category=Category.DEFECT, confidence=0.9), extraction


# 기획서 5.5 예시 (불량 문의)


def test_defect_example_fills_known_fields_and_marks_the_rest_missing() -> None:
    classification, extraction = _defect()

    form = fill_form(classification, extraction, S100_CHAT, tables=TABLES)

    assert form.category == "DEFECT"
    assert form.product_code == "INV-LSLV0075-S100"
    assert form.fields == {
        "product_model": "LSLV S100 7.5kW VFD",
        "error_code": "E.OC",
        "operating_condition": "during acceleration",
    }
    # DRIVE · DEFECT 필수 항목 중 대화에 없던 것 (시리얼 번호, 사진·로그 …)
    assert form.missing_required == [
        "serial_no",
        "photos",
        "logs",
        "parameter_backup",
        "motor_nameplate",
    ]


def test_required_fields_come_from_the_rule_table() -> None:
    classification, extraction = _defect()

    form = fill_form(classification, extraction, S100_CHAT, tables=TABLES)

    required = set(TABLES.required[("DRIVE", "DEFECT")][0])
    assert (set(form.fields) & required) | set(form.missing_required) == required
    assert not set(form.fields) & set(form.missing_required)


def test_serial_and_firmware_are_mapped_to_field_names() -> None:
    classification = Classification(category=Category.FW_UPDATE, confidence=0.9)
    extraction = Extraction(
        product_code="INV-LSLV0075-S100",
        product_family="DRIVE",
        serial_no="SN-123",
        fw_version="1.2.3",
    )

    form = fill_form(classification, extraction, [], tables=TABLES)

    assert form.fields["serial_no"] == "SN-123"
    assert form.fields["current_fw"] == "1.2.3"


def test_field_values_win_over_scalar_extraction_fields() -> None:
    classification, extraction = _defect()
    extraction = extraction.model_copy(update={"field_values": {"error_code": "E.OC (confirmed)"}})

    form = fill_form(classification, extraction, [], tables=TABLES)

    assert form.fields["error_code"] == "E.OC (confirmed)"


def test_blank_and_unknown_values_are_not_filled() -> None:
    classification, extraction = _defect()
    extraction = extraction.model_copy(
        update={"field_values": {"serial_no": "  ", "not_a_field": "x", "photos": ""}}
    )

    form = fill_form(classification, extraction, [], tables=TABLES)

    assert "serial_no" in form.missing_required
    assert "photos" in form.missing_required
    assert "not_a_field" not in form.fields


def test_unknown_product_asks_for_product_model() -> None:
    classification = Classification(category=Category.QUOTE, confidence=0.9)

    form = fill_form(classification, Extraction(), [], tables=TABLES)

    assert form.product_code is None
    assert "product_model" in form.missing_required
    assert form.fields == {}


def test_family_is_taken_from_product_code_when_missing() -> None:
    classification = Classification(category=Category.QUOTE, confidence=0.9)
    extraction = Extraction(product_code="ESS-PCS-100kW")

    form = fill_form(classification, extraction, [], tables=TABLES)

    required = set(form.fields) | set(form.missing_required)
    assert required == set(TABLES.required[("ESS", "QUOTE")][0])


def test_default_tables_are_loaded_when_omitted() -> None:
    classification, extraction = _defect()

    assert fill_form(classification, extraction, []).fields["error_code"] == "E.OC"


# 제목·본문


SUMMARY = """Repeated E.OC after adjusting acceleration time

The LSLV S100 trips with E.OC during acceleration. We already tried increasing the acceleration
time (F23), but the fault came back."""


def test_summary_is_written_by_llm_with_chat_and_advice_in_prompt() -> None:
    classification, extraction = _defect()
    writer = ScriptedWriter(SUMMARY)

    form = fill_form(classification, extraction, S100_CHAT, llm=live(writer), tables=TABLES)

    assert form.subject == "Repeated E.OC after adjusting acceleration time"
    assert form.body.startswith("The LSLV S100 trips with E.OC")
    prompt = writer.prompts[0]
    assert "S100 가속 중에 E.OC 가 떠요" in prompt  # 고객 말
    assert "가속 시간(F23)을 늘려 보세요" in prompt  # 이미 안내한 조치
    assert "E.OC" in prompt


def test_prompt_separates_customer_messages_from_chatbot_advice() -> None:
    classification, extraction = _defect()
    writer = ScriptedWriter(SUMMARY)

    fill_form(classification, extraction, S100_CHAT, llm=live(writer), tables=TABLES)

    prompt = writer.prompts[0]
    assert prompt.index("S100 가속 중에 E.OC 가 떠요") < prompt.index(
        "가속 시간(F23)을 늘려 보세요"
    )
    assert "해결되지 않아 상담원에게" in prompt


def test_fallback_summary_when_llm_is_off() -> None:
    classification, extraction = _defect()

    form = fill_form(
        classification,
        extraction,
        S100_CHAT,
        llm=LLMRouter(Settings(_env_file=None)),
        tables=TABLES,
    )

    assert form.subject == "S100 가속 중에 E.OC 가 떠요"
    assert "가속 시간을 늘렸는데도 다시 E.OC 가 발생해요" in form.body
    assert "가속 시간(F23)을 늘려 보세요" in form.body  # 이미 안내한 조치도 남긴다


def test_fallback_summary_when_llm_fails() -> None:
    classification, extraction = _defect()
    writer = ScriptedWriter(RuntimeError("boom"))

    form = fill_form(classification, extraction, S100_CHAT, llm=live(writer), tables=TABLES)

    assert form.subject == "S100 가속 중에 E.OC 가 떠요"
    assert form.fields["error_code"] == "E.OC"  # 요약이 실패해도 칸은 채워진다


@pytest.mark.parametrize("bad", ["", "   ", "제목만 있고 본문이 없다"])
def test_fallback_summary_when_llm_output_has_no_subject_and_body(bad: str) -> None:
    classification, extraction = _defect()

    form = fill_form(
        classification, extraction, S100_CHAT, llm=live(ScriptedWriter(bad)), tables=TABLES
    )

    assert form.subject == "S100 가속 중에 E.OC 가 떠요"


def test_empty_chat_gives_empty_subject_and_body_without_calling_llm() -> None:
    classification, extraction = _defect()
    writer = ScriptedWriter()

    form = fill_form(classification, extraction, [], llm=live(writer), tables=TABLES)

    assert (form.subject, form.body) == ("", "")
    assert writer.prompts == []


def test_long_first_message_is_cut_for_the_fallback_subject() -> None:
    classification, extraction = _defect()

    form = fill_form(classification, extraction, ["x" * 500], tables=TABLES)

    assert len(form.subject) <= 100


def test_form_matches_the_shape_the_screen_expects() -> None:
    classification, extraction = _defect()

    form = fill_form(classification, extraction, S100_CHAT, tables=TABLES)

    assert isinstance(form, InquiryDraftForm)
    assert set(form.model_dump()) == {
        "category",
        "product_code",
        "fields",
        "missing_required",
        "subject",
        "body",
    }


def test_known_values_outside_the_required_list_are_kept() -> None:
    """기술사양 문의에도 대화에서 찾은 에러코드·시리얼은 상담원에게 넘긴다."""
    classification = Classification(category=Category.TECH_SPEC, confidence=0.9)
    extraction = Extraction(product_code="INV-LSLV0075-S100", error_code="E.OC", serial_no="SN-1")

    form = fill_form(classification, extraction, [], tables=TABLES)

    assert list(form.fields)[0] == "product_model"  # 필수 항목이 앞
    assert form.fields["error_code"] == "E.OC" and form.fields["serial_no"] == "SN-1"
    assert "error_code" not in form.missing_required


@pytest.mark.parametrize(
    ("language", "label"),
    [("ko", "챗봇에서 이미 안내받은 조치:"), ("de-DE", "Bereits im Chat empfohlen:"),
     (None, "Already advised in chat:"), ("xx", "Already advised in chat:")],
)  # fmt: skip
def test_fallback_summary_labels_follow_customer_language(language, label) -> None:
    classification, extraction = _defect(language=language)

    form = fill_form(classification, extraction, S100_CHAT, tables=TABLES)

    assert label in form.body
