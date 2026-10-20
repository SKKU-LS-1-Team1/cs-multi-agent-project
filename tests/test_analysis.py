"""CSA-26 회귀 검사. 실제 API·대기 없이 판단/추출 경계와 장애 처리를 확인한다."""

import json
from types import SimpleNamespace

import httpx
import pytest

from cs_agent.agents import analysis as a
from cs_agent.config import Settings
from cs_agent.domain import Category, Urgency
from cs_agent.rules.tables import load_tables
from cs_agent.schemas import InquiryIn

S100 = "INV-LSLV0075-S100"
IS7 = "INV-LSLV0750-iS7"


class JudgeStub:
    def __init__(self, error=None):
        self.error = error

    def judge(self, task, prompt, options):
        assert task == "extract_urgency"
        if self.error:
            raise self.error
        return SimpleNamespace(answer="NONE", confidence=0.9, model="jev-test")


class ExtractorStub:
    def __init__(self, response=None, error=None):
        self.response = response if response is not None else {"fields": {}, "model": "gemini-test"}
        self.error = error
        self.calls = []

    def extract_structured(self, task, prompt, schema, *, model):
        self.calls.append({"input": json.loads(prompt), "model": model})
        if self.error:
            raise self.error
        return self.response


@pytest.fixture
def settings():
    return Settings(_env_file=None, llm_provider="fake", gemini_model_fast="gemini-test")


@pytest.fixture
def tables(settings):
    return load_tables(settings.ref_dir)


def details(inquiry, tables, settings, extractor, **kwargs):
    return a.extract_details(
        inquiry,
        tables,
        settings=settings,
        llm=JudgeStub(),
        extractor=extractor,
        **kwargs,
    )


@pytest.mark.parametrize(
    "extractor",
    [
        ExtractorStub(error=TimeoutError("provider unavailable")),
        ExtractorStub(response={"fields": {"quantity": {"value": 3}}, "model": "gemini-test"}),
    ],
    ids=["provider-timeout", "invalid-response"],
)
def test_extraction_failure_returns_grounded_rules_and_records_issue(tables, settings, extractor):
    inquiry = InquiryIn(
        channel="EMAIL",
        body="S100. Error code: E.OC. S/N SN12345. Current firmware: 1.2.3",
    )
    result = details(inquiry, tables, settings, extractor, requested_fields=["quantity"])

    assert "structured_extraction_failed" in result.issues
    assert len(result.extraction_errors) == 1
    output = result.to_extraction()
    assert output.product_code == S100
    assert output.product_family == "DRIVE"
    assert output.error_code == "E.OC"
    assert output.serial_no == "SN12345"
    assert output.fw_version == "1.2.3"
    assert output.urgency == Urgency.NONE
    assert set(output.provided_info) == {"product_model", "error_code", "serial_no", "current_fw"}
    assert "structured_extraction_failed" in result.issues

    # 그래프가 사용하는 공개 함수에서도 같은 대체 경로를 사용한다.
    assert (
        a.extract(
            inquiry,
            tables,
            settings=settings,
            llm=JudgeStub(),
            extractor=extractor,
            category=Category.DEFECT,
            requested_fields=["quantity"],
        )
        == output
    )


def test_extraction_failure_does_not_hide_missing_urgency(tables, settings):
    result = a.extract_details(
        InquiryIn(channel="EMAIL", body="S100"),
        tables,
        settings=settings,
        llm=JudgeStub(error=RuntimeError("judges unavailable")),
        extractor=ExtractorStub(error=TimeoutError()),
        requested_fields=["quantity"],
    )
    assert "structured_extraction_failed" in result.issues
    with pytest.raises(a.AnalysisError, match="urgency_unassessed"):
        result.to_extraction()


def test_safety_review_keeps_human_route_without_waiting_for_extraction(tables, settings):
    extractor = ExtractorStub(error=TimeoutError())
    result = details(
        InquiryIn(channel="EMAIL", body="S100. There is no smoke or fire."),
        tables,
        settings,
        extractor,
        requested_fields=["quantity"],
    )
    assert result.urgency == Urgency.NONE
    assert "safety_mention_requires_review" in result.issues
    assert result.to_extraction().urgency == Urgency.SAFETY
    assert not extractor.calls


def test_latest_correction_overrides_title_and_saved_product(tables, settings):
    inquiry = InquiryIn(
        channel="CHAT",
        subject="iS7 문의",
        body="S100으로 정정합니다.",
        product_code=IS7,
        provided_fields={"product_model": IS7},
    )
    original = inquiry.model_dump()
    extractor = ExtractorStub(
        response={
            "fields": {"product_model": {"value": "S100", "evidence": inquiry.body}},
            "model": "gemini-test",
        }
    )
    result = details(
        inquiry,
        tables,
        settings,
        extractor,
        requested_fields=[],
        transcript=[
            {"role": "user", "content": "제품은 iS7입니다."},
            {"role": "assistant", "content": "XGI 제품인가요?"},
        ],
    )
    assert result.to_extraction().product_code == S100
    assert result.evidence["product_model"] == inquiry.body
    assert any(c["value"] == IS7 for c in result.field_candidates["product_model"])
    assert extractor.calls[0]["input"]["customer_messages"] == ["제품은 iS7입니다."]
    assert inquiry.model_dump() == original


def test_unknown_product_rejects_model_reusing_earlier_evidence(tables, settings):
    previous = "제품은 iS7입니다."
    inquiry = InquiryIn(
        channel="CHAT",
        body="제품 모델은 모르겠습니다.",
        product_code=IS7,
    )
    extractor = ExtractorStub(
        response={
            "fields": {"product_model": {"value": "iS7", "evidence": previous}},
            "model": "gemini-test",
        }
    )
    result = details(
        inquiry,
        tables,
        settings,
        extractor,
        requested_fields=[],
        transcript=[{"role": "user", "content": previous}],
    )
    assert result.to_extraction().product_code is None
    assert "product_model" not in result.provided_info
    assert result.unconfirmed_fields["product_model"] == "UNKNOWN"
    assert result.unconfirmed_evidence["product_model"] == inquiry.body


def test_failed_extraction_preserves_unaffected_fields_but_not_withdrawn_serial(tables, settings):
    inquiry = InquiryIn(
        channel="CHAT",
        body="Ignore the previous serial number. Error code: E.OC.",
        product_code=S100,
        provided_fields={"serial_no": "OLD123"},
    )
    result = details(
        inquiry,
        tables,
        settings,
        ExtractorStub(error=TimeoutError()),
        requested_fields=[],
        transcript=[{"role": "user", "content": "S100. S/N OLD123."}],
    )
    output = result.to_extraction()
    assert "structured_extraction_failed" in result.issues
    assert output.product_code == S100
    assert output.error_code == "E.OC"
    assert output.serial_no is None
    assert "serial_no" not in output.provided_info
    assert result.unconfirmed_fields["serial_no"] == "RETRACTED"
    assert result.unconfirmed_evidence["serial_no"] == inquiry.body
    assert result.field_candidates["serial_no"][0]["value"] == "OLD123"


@pytest.mark.parametrize("override", [None, "explicit-model"])
def test_default_adapter_uses_model_from_env(tmp_path, monkeypatch, tables, override):
    monkeypatch.delenv("GEMINI_MODEL_FAST", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("GEMINI_MODEL_FAST=environment-model\n", encoding="utf-8")
    settings = Settings(_env_file=env_file, llm_provider="live", gemini_api_key="test-only-key")
    extractor = ExtractorStub()
    selected = []

    def adapter(api_key, model):
        selected.append(model)
        return extractor

    monkeypatch.setattr(a, "_gemini_extractor", adapter)
    result = a.extract_details(
        InquiryIn(channel="EMAIL", body="S100 quotation"),
        tables,
        settings=settings,
        llm=JudgeStub(),
        category=Category.QUOTE,
        requested_fields=["quantity"],
        extraction_model=override,
    )
    expected = override or "environment-model"
    assert selected == [expected]
    assert extractor.calls[0]["model"] == expected
    assert "structured_extraction_failed" not in result.issues


class Clock:
    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


def sdk_response(fields=None):
    return {
        "parsed": {"fields": fields or {}},
        "parsing_error": None,
        "raw": SimpleNamespace(response_metadata={"model_name": "gemini-test"}),
    }


class ChatStub:
    """실제 SDK에 넘기는 제한 시간을 기록하고 응답 시간만큼 가상 시계를 진행한다."""

    def __init__(self, clock, actions):
        self.clock = clock
        self.actions = iter(actions)
        self.options = []

    def model_copy(self, *, update):
        self.options.append(update)
        return self

    def with_structured_output(self, schema, *, method, include_raw):
        assert method == "json_schema" and include_raw
        return self

    def invoke(self, prompt):
        elapsed, response = next(self.actions)
        self.clock.now += elapsed
        if isinstance(response, Exception):
            raise response
        return response


@pytest.fixture
def native(monkeypatch):
    clock = Clock()
    monkeypatch.setattr(a, "time", clock)

    def make(actions):
        extractor = a._GeminiExtractor("test-only-key", "gemini-test")
        chat = ChatStub(clock, actions)
        extractor.__dict__["_chat"] = chat
        return extractor, chat, clock

    return make


def http_error(status):
    request = httpx.Request("POST", "https://example.invalid/extraction")
    response = httpx.Response(status, request=request)
    return httpx.HTTPStatusError("test status", request=request, response=response)


def invoke(extractor, **kwargs):
    return extractor.extract_structured("extract_fields", "test", {}, model="gemini-test", **kwargs)


def test_transient_retry_uses_remaining_total_budget_and_disables_sdk_retries(native):
    extractor, chat, clock = native([(45, http_error(504)), (10, sdk_response())])
    assert invoke(extractor)["fields"] == {}
    assert chat.options == [
        {"timeout": 45.0, "max_retries": 0},
        {"timeout": 14.5, "max_retries": 0},
    ]
    assert clock.sleeps == [0.5]


def test_only_one_retry_after_repeated_transient_errors(native):
    extractor, chat, clock = native([(1, http_error(503)), (1, http_error(503))])
    with pytest.raises(httpx.HTTPStatusError):
        invoke(extractor)
    assert len(chat.options) == 2
    assert clock.sleeps == [0.5]


@pytest.mark.parametrize("status", [400, 401, 403, 404])
def test_non_transient_errors_are_not_retried(native, status):
    extractor, chat, clock = native([(1, http_error(status))])
    with pytest.raises(httpx.HTTPStatusError):
        invoke(extractor)
    assert len(chat.options) == 1
    assert not clock.sleeps


def test_parsing_failure_is_not_retried(native):
    response = {"parsed": None, "parsing_error": ValueError("invalid JSON")}
    extractor, chat, clock = native([(1, response)])
    with pytest.raises(ValueError, match="Invalid structured extraction response"):
        invoke(extractor)
    assert len(chat.options) == 1
    assert not clock.sleeps


def test_wrapped_network_timeout_is_retried(native):
    error = RuntimeError("SDK wrapper")
    error.__cause__ = httpx.ReadTimeout("provider timeout")
    extractor, chat, _ = native([(1, error), (1, sdk_response())])
    assert invoke(extractor)["fields"] == {}
    assert len(chat.options) == 2


def test_expired_deadline_does_not_call_provider(native):
    extractor, chat, _ = native([])
    with pytest.raises(TimeoutError, match="deadline_exceeded"):
        invoke(extractor, deadline=0)
    assert not chat.options


def test_late_response_is_rejected(native):
    extractor, chat, _ = native([(61, sdk_response())])
    with pytest.raises(TimeoutError, match="deadline_exceeded"):
        invoke(extractor)
    assert len(chat.options) == 1


def test_budget_exhaustion_does_not_start_retry(native):
    extractor, chat, clock = native([(59.8, http_error(504))])
    with pytest.raises(TimeoutError, match="deadline_exceeded"):
        invoke(extractor)
    assert len(chat.options) == 1
    assert not clock.sleeps


def test_additional_fields_after_product_correction_share_total_budget(native, tables, settings):
    inquiry = InquiryIn(
        channel="CHAT",
        body="Correction: product model is XGI.",
        product_code=S100,
    )
    extractor, chat, clock = native(
        [
            (
                40,
                sdk_response({"product_model": {"value": "XGI", "evidence": inquiry.body}}),
            ),
            (10, sdk_response()),
        ]
    )
    result = details(
        inquiry,
        tables,
        settings,
        extractor,
        category=Category.DEFECT,
        transcript=[{"role": "user", "content": "S100 has a fault."}],
    )
    assert result.to_extraction().product_code == "PLC-XGI-CPUU"
    assert chat.options == [
        {"timeout": 45.0, "max_retries": 0},
        {"timeout": 20.0, "max_retries": 0},
    ]
    assert clock.now == 50
    assert "structured_extraction_failed" not in result.issues
