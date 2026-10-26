"""Final-language QC blocks approval regardless of the old verification override."""

import json
import threading
from contextlib import contextmanager

import pytest
from test_approval_verification import setup_graph

from cs_agent.agents import customer_qc as qc
from cs_agent.config import Settings
from cs_agent.llm.clients import Completion
from cs_agent.llm.router import LLMRouter
from cs_agent.qc_schemas import QcResult
from cs_agent.schemas import Evidence


class Writer:
    name = "qc-test"

    def __init__(self, result):
        self.result = result
        self.prompts = []

    def write(self, prompt):
        self.prompts.append(prompt)
        if isinstance(self.result, Exception):
            raise self.result
        return Completion(json.dumps(self.result), self.name)


def router(result):
    writer = Writer(result)
    return LLMRouter(Settings(_env_file=None, llm_provider="live"), writer=writer), writer


def finding(category="ABUSE", source_id=None, paragraph="p1", decision="BLOCK"):
    return {
        "decision": decision,
        "issues": [{"paragraph_id": paragraph, "category": category, "source_id": source_id}],
    }


@pytest.mark.parametrize(
    "text,language",
    [
        ("Merci pour votre demande.", "fr"),
        ("شكراً لتواصلك معنا.", "ar"),
        ("感谢您的来信。", "zh"),
        ("Gracias por contactarnos.", "es"),
    ],
)
def test_final_language_only_is_passed_to_model(text, language):
    llm, writer = router({"decision": "PASS", "issues": []})
    result = qc.check_final(text, language, llm)
    assert result.decision == "PASS"
    payload = json.loads(writer.prompts[0].split("\nINPUT:\n")[1])
    assert payload == {
        "final_text": {"p1": text},
        "target_language": language,
        "restricted_context": [],
    }
    assert "source_text" not in payload
    assert len(result.text_hash) == 64


def test_credential_rule_blocks_without_sending_secret_to_model():
    llm, writer = router({"decision": "PASS", "issues": []})
    secret = "sk-" + "TESTONLY" * 5
    result = qc.check_final(f"API key: {secret}", "en", llm)
    assert result.decision == "BLOCK"
    assert result.issues[0]["category"] == "CREDENTIAL"
    assert not writer.prompts
    assert secret not in result.model_dump_json()


@pytest.mark.parametrize(
    "text",
    [
        "Product iS7; serial 1234567890.",
        "Please reset your password.",
        "The quoted price is USD 200.",
    ],
)
def test_codes_reset_instructions_prices_are_not_rule_blocked(text):
    llm, writer = router({"decision": "PASS", "issues": []})
    assert qc.check_final(text, "en", llm).decision == "PASS"
    assert len(writer.prompts) == 1


@pytest.mark.parametrize(
    "answer",
    [
        finding(),
        finding("CREDENTIAL"),
        finding("CONFIDENTIAL", "internal#1"),
        finding("CONFIDENTIAL", "internal#1", decision="REVIEW"),
    ],
)
def test_model_issues_return_safe_korean_reasons(answer):
    llm, _ = router(answer)
    result = qc.check_final(
        "Final text.",
        "en",
        llm,
        restricted_context=[{"source_id": "internal#1", "text": "고객 공개 금지: 내부 조건"}],
    )
    assert result.decision == answer["decision"]
    assert result.issues[0]["reason"] and result.issues[0]["suggestion"]
    assert "excerpt" not in result.issues[0]


@pytest.mark.parametrize(
    "answer",
    [
        {"decision": "PASS", "issues": [finding()["issues"][0]]},
        {"decision": "BLOCK", "issues": []},
        finding(paragraph="p999"),
        finding("CONFIDENTIAL", "invented"),
        finding(decision="REVIEW"),
        {"decision": "APPROVE", "issues": []},
    ],
)
def test_invalid_response_or_invented_confidentiality_does_not_pass(answer):
    llm, _ = router(answer)
    assert qc.check_final("Final text", "en", llm).decision == "ERROR"


def test_only_explicitly_restricted_sources_are_provided():
    rows = [
        Evidence(source="specialist", doc_id="ordinary", text="Internal technical note."),
        Evidence(
            source="docs",
            doc_id="marked",
            text="Restricted terms",
            metadata={"customer_disclosure": "prohibited"},
        ),
        Evidence(source="specialist", doc_id="labelled", text="고객 공개 금지: 비용 조건"),
    ]
    assert [r["source_id"] for r in qc.restricted_sources(rows)] == ["marked#", "labelled#"]


def test_disabled_llm_and_model_exception_fail_closed():
    assert qc.check_final("Hello", "en", LLMRouter(Settings(_env_file=None))).decision == "ERROR"
    llm, _ = router(RuntimeError("private response"))
    result = qc.check_final("Hello", "en", llm)
    assert result.decision == "ERROR"
    assert "private response" not in result.model_dump_json()


def test_timeout_does_not_wait_for_late_result_or_approve(monkeypatch):
    entered, release, done = threading.Event(), threading.Event(), threading.Event()
    llm, writer = router({"decision": "PASS", "issues": []})

    def slow(prompt):
        entered.set()
        release.wait(2)
        done.set()
        return Completion('{"decision":"PASS","issues":[]}', "test")

    writer.write = slow
    monkeypatch.setattr(qc, "TIMEOUT_S", 0.02)
    try:
        result = qc.check_final("Hello", "en", llm)
        assert entered.is_set() and result.decision == "ERROR"
    finally:
        release.set()
        assert done.wait(2)


def test_qc_does_not_cache_or_trace_raw_content(monkeypatch):
    from cs_agent.llm import router as module

    spans = []

    @contextmanager
    def trace(task, model, prompt, **kwargs):
        from types import SimpleNamespace

        span = SimpleNamespace(output=None, usage=None)
        spans.append((prompt, span))
        yield span

    monkeypatch.setattr(module, "trace", trace)
    llm, writer = router({"decision": "PASS", "issues": []})
    llm._cache_set = lambda *a: pytest.fail("QC must not be cached")
    for _ in range(2):
        assert qc.check_final("sensitive final text", "en", llm).decision == "PASS"
    assert len(writer.prompts) == 2
    assert all("sensitive" not in p and s.output == "[QC output omitted]" for p, s in spans)


@pytest.mark.parametrize("decision", ["BLOCK", "REVIEW", "ERROR"])
def test_qc_cannot_be_overridden_and_exact_translation_is_checked(decision):
    seen = []

    def check(text, language, llm, **kwargs):
        seen.append((text, language))
        return QcResult(decision=decision, issues=[{"paragraph_id": "p1", "category": "ABUSE"}])

    graph, config, act, _, _ = setup_graph(language="fr", qc=check)
    for _ in range(2):
        result = act(action="approve", reviewer="staff", acknowledged_failures=True)
        assert result["status"] == "ON_HOLD"
        assert not result["final_reply"]
        assert not any(e["kind"] == "sent" for e in result.get("processing_history", []))
        assert result["customer_qc"]["decision"] == decision
    assert seen == [("Réponse vérifiée.", "fr")] * 2


def test_qc_retry_success_records_once_and_does_not_rewrite_staff_text():
    outcomes = iter([QcResult(decision="ERROR"), QcResult(decision="PASS")])
    graph, config, act, _, _ = setup_graph(qc=lambda *a, **k: next(outcomes))
    edited = "Please refer to the updated installation guide."
    first = act(action="edit_approve", edited_text=edited)
    assert first["approval_text"] == edited and first["status"] == "ON_HOLD"
    second = act(action="approve")
    assert second["status"] == "APPROVED" and second["final_reply"] == edited
    assert len([e for e in second["processing_history"] if e["kind"] == "sent"]) == 1


def test_info_request_is_also_checked_and_edit_is_retained():
    seen = []
    outcomes = iter([QcResult(decision="BLOCK"), QcResult(decision="PASS")])

    def check(text, language, llm, **kwargs):
        seen.append(text)
        return next(outcomes)

    graph, config, act, _, _ = setup_graph(qc=check)
    graph.update_state(
        config,
        {"pending": "info_request", "info_request": "Please send the serial number."},
        as_node="ready",
    )
    result = act(action="edit_approve", edited_text="Please send the model and serial number.")
    assert result["status"] == "ON_HOLD" and result["final_reply"] is None
    result = act(action="approve", reviewer="staff", acknowledged_failures=True)
    assert result["status"] == "WAITING_CUSTOMER"
    assert seen == ["Please send the model and serial number."] * 2


def test_progress_preparation_is_blocked_and_retry_can_recover(client, notices):
    from test_progress_service import approval_path, create, submit

    service, _, _ = notices
    ticket = submit(client)
    response, _ = create(client, ticket)
    notice = response.json()
    seen = []

    def block(text, language, llm):
        seen.append((text, language))
        return QcResult(decision="BLOCK")

    service.check_customer_qc = block
    path = approval_path(ticket["ticket_id"], notice)
    body = {"edited_text": "Your response is awaiting review.", "reviewer": "staff"}
    row = client.post(path, json=body).json()
    assert row["status"] == "draft" and row["final_text"] is None
    assert row["customer_qc"]["decision"] == "BLOCK"
    assert seen[0][0].startswith("Votre demande") and seen[0][1] == "fr"
    service.check_customer_qc = lambda *a, **k: QcResult(decision="PASS")
    assert client.post(path, json=body).json()["status"] == "prepared"


# Explicitly reuse the existing API/notice fixtures, never a global QC bypass.
from test_api import client as client  # noqa: E402
from test_progress_service import notices as notices  # noqa: E402


def test_api_exposes_qc_block_and_retry_without_recording_a_failed_send():
    from fastapi.testclient import TestClient
    from stubs import ANALYSIS, pass_customer_qc
    from test_api import INQUIRY

    from cs_agent.main import create_app

    calls = []

    def checker(text, language, llm, **kwargs):
        calls.append(text)
        if len(calls) == 1:
            return QcResult(decision="BLOCK", issues=[qc._issue("p1", "ABUSE")])
        return pass_customer_qc(text)

    with TestClient(
        create_app(
            llm=LLMRouter(Settings(_env_file=None)),
            agents={**ANALYSIS, "check_customer_qc": checker},
            storage="memory",
            retrievers=(None, None),
        )
    ) as api:
        tid = api.post("/api/tickets", json=INQUIRY).json()["ticket_id"]
        blocked = api.post(
            f"/api/tickets/{tid}/action",
            json={"action": "approve", "reviewer": "staff", "acknowledged_failures": True},
        ).json()
        assert blocked["status"] == "ON_HOLD"
        assert blocked["customer_qc"]["decision"] == "BLOCK"
        assert blocked["final_reply"] is None
        assert not any(e["kind"] == "sent" for e in blocked["processing_history"])
        sent = api.post(
            f"/api/tickets/{tid}/action", json={"action": "approve", "reviewer": "staff"}
        ).json()
        assert sent["status"] == "APPROVED"
        assert sent["customer_qc"]["decision"] == "PASS"
        assert calls == [sent["final_reply"]] * 2
        assert len([e for e in sent["processing_history"] if e["kind"] == "sent"]) == 1
        duplicate = api.post(f"/api/tickets/{tid}/action", json={"action": "approve"})
        assert duplicate.status_code == 409
        assert len(calls) == 2
