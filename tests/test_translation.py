import json
import time
from threading import Event

import pytest
import stubs
from fastapi.testclient import TestClient
from test_db import TEST_DATABASE_URL, needs_db
from test_db import db as db

from cs_agent.agents import translation as t
from cs_agent.cache.store import MemoryKV
from cs_agent.config import Settings
from cs_agent.domain import Category
from cs_agent.graph.builder import GraphDeps, build_ticket_graph, serializer
from cs_agent.llm import tracing
from cs_agent.llm.clients import Completion
from cs_agent.llm.router import LLMRouter
from cs_agent.main import create_app
from cs_agent.schemas import InquiryIn
from cs_agent.services.tickets import TicketService


class Writer:
    name = "translation-test"

    def __init__(self, text="", error=None):
        self.text, self.error, self.prompts = text, error, []

    def write(self, prompt):
        self.prompts.append(prompt)
        if self.error:
            raise self.error
        return Completion(self.text, self.name)


def router(writer=None, **settings):
    return LLMRouter(
        Settings(_env_file=None, llm_provider="live" if writer else "fake", **settings),
        writer=writer,
        kv=MemoryKV(),
    )


@pytest.mark.parametrize(
    "language",
    ["en", "es", "fr", "th", "it", "id", "zh", "tr", "ar", "ru", "vi", "pt", "de", "ja", "pl"],
)
def test_customer_language_hint_does_not_limit_translation(language):
    # 언어 힌트가 달라도 입력 원문을 그대로 보낸다. 실제 언어별 품질 평가는 별도 실측이다.
    writer = Writer("S100에 오류 E.OC가 표시됩니다. 전원은 220 V입니다.")
    source = "S100 displays E.OC. Supply is 220 V."
    assert t.translate_to_korean(source, language, router(writer)) == writer.text
    payload = json.loads(writer.prompts[0].removeprefix(t.TRANSLATION_INSTRUCTIONS + "\n\n"))
    assert payload["source_text"] == source
    assert payload["reply_language_hint"] == language


def test_preserves_technical_values_mask_and_attachment():
    source = (
        "INV-LSLV0075-S100: E.OC; S/N AB12345; 220 V; 25 °C; IEC 60947-2. "
        "No smoke. [attachment: 6 photos] **MASKED**"
    )
    translated = (
        "INV-LSLV0075-S100: E.OC; S/N AB12345; 220 V; 25 °C; IEC 60947-2. "
        "연기는 없습니다. [attachment: 6 photos] **MASKED**"
    )
    assert t.translate_to_korean(source, "en", router(Writer(translated))) == translated
    assert "IEC 60947-2" in t.protected_terms(source)
    assert "220 V" in t.protected_terms(source)


@pytest.mark.parametrize("text", ["", "S100 제품에서 E.OC 오류가 발생합니다.", "S100 220 V"])
def test_korean_or_empty_input_does_not_call_model(text):
    writer = Writer(error=AssertionError("must not call"))
    assert t.translate_to_korean(text, "en", router(writer)) is None
    assert not writer.prompts


def test_korean_reply_preference_does_not_skip_foreign_or_mixed_body():
    writer = Writer("S100에서 연기는 없고 소음만 있습니다.")
    assert t.translate_to_korean("S100에는 no smoke, only noise.", "ko", router(writer))
    assert len(writer.prompts) == 1


@pytest.mark.parametrize(
    "bad",
    [
        "S100의 전압은 230 V입니다.",
        "S200의 전압은 220 V입니다.",
        "S100의 전압은 220 V이며 10 A입니다.",
        "",
        "Supply voltage of S100 is 220 V.",
    ],
)
def test_invalid_translation_is_not_cached_as_success(bad):
    source = "S100 supply is 220 V."
    writer = Writer(bad)
    llm = router(writer)
    assert t.translate_to_korean(source, "en", llm) is None
    writer.text = "S100의 전원은 220 V입니다."
    assert t.translate_to_korean(source, "en", llm) == writer.text
    assert t.translate_to_korean(source, "en", llm) == writer.text
    assert len(writer.prompts) == 2  # 거절 응답 재호출, 정상 응답은 캐시 재사용


def test_api_failure_and_offline_are_none():
    assert t.translate_to_korean("Please help", "en", router(Writer(error=TimeoutError()))) is None
    assert t.translate_to_korean("Please help", "en", router()) is None


def test_validator_failure_also_returns_none(monkeypatch):
    def broken(*args):
        raise RuntimeError("validator unavailable")

    monkeypatch.setattr(t, "check_language", broken)
    assert t.translate_to_korean("Please help", "en", router(Writer("도와주세요."))) is None


def test_saturated_translation_workers_do_not_queue_more_calls(monkeypatch):
    from threading import BoundedSemaphore

    capacity = BoundedSemaphore(1)
    capacity.acquire()
    monkeypatch.setattr(t, "_CAPACITY", capacity)

    def forbidden(*args):
        pytest.fail("saturated pool must not start or queue another call")

    translated, parts = t.translate_parts("Please help", "en", [], forbidden, router())
    assert translated is None and parts[0]["ko"] is None


def inquiry(body="Please provide dimensions for TRF-OIL-1000."):
    return InquiryIn(
        channel="email",
        language="en",
        body=body,
        category=Category.TECH_SPEC,
        product_code="TRF-OIL-1000",
        provided_fields={"application": "substation"},
    )


def service(translate, llm=None, checkpointer=None, records=None):
    deps = GraphDeps(llm=llm or router(), **stubs.ANALYSIS, translate=translate)
    return TicketService(build_ticket_graph(deps, checkpointer), records)


def test_reply_translates_only_new_part_and_restores_checkpoint():
    calls = []

    def translate(text, language, llm):
        calls.append((text, tracing._ticket_id.get()))
        return "번역: " + text

    svc = service(translate)
    original = inquiry()
    ticket = svc.submit(original)
    assert ticket.body_ko == "번역: " + original.body
    assert svc.records.tickets[ticket.ticket_id]["body"] == original.body
    assert svc.records.tickets[ticket.ticket_id]["body_ko"] == ticket.body_ko
    state = svc._state(ticket.ticket_id).values
    assert (
        serializer().loads_typed(serializer().dumps_typed(state))["translation_parts"]
        == state["translation_parts"]
    )
    # 같은 체크포인터와 저장소를 새 서비스에서 읽고 회신한다.
    restored = service(translate, checkpointer=svc.graph.checkpointer, records=svc.records)
    assert restored.get(ticket.ticket_id).body_ko == ticket.body_ko
    result = restored.reply(ticket.ticket_id, inquiry("Also provide weight."))
    assert [c[0] for c in calls] == [original.body, "Also provide weight."]
    assert all(c[1] == ticket.ticket_id for c in calls)  # worker에도 Langfuse 문맥 전달
    assert result.body_ko.count("번역:") == 2
    assert "Customer reply" in result.body_ko
    restored._run(
        ticket.ticket_id, {"inquiry": restored._state(ticket.ticket_id).values["inquiry"]}
    )
    assert len(calls) == 2


def test_partial_failure_does_not_show_stale_or_incomplete_translation():
    calls = []
    fail = True

    def translate(text, language, llm):
        calls.append(text)
        return None if fail and text == "New reply." else "번역: " + text

    svc = service(translate)
    first = svc.submit(inquiry())
    second = svc.reply(first.ticket_id, inquiry("New reply."))
    assert second.body_ko is None
    assert svc.records.tickets[first.ticket_id]["body_ko"] is None
    fail = False
    svc._run(first.ticket_id, {"inquiry": svc._state(first.ticket_id).values["inquiry"]})
    assert calls == [inquiry().body, "New reply.", "New reply."]
    assert svc.get(first.ticket_id).body_ko.count("번역:") == 2


def test_korean_initial_message_is_retained_when_foreign_reply_arrives():
    calls = []

    def translate(text, language, llm):
        calls.append(text)
        return "추가 정보도 알려주세요."

    svc = service(translate)
    first = svc.submit(inquiry("제품 사양을 알려주세요."))
    assert first.body_ko is None and not calls
    result = svc.reply(first.ticket_id, inquiry("Please provide more information."))
    assert result.body_ko.startswith("제품 사양을 알려주세요.")
    assert len(calls) == 1


def test_changed_body_discards_old_translation():
    old = [t.new_part("Old text.", "en")]
    old[0]["ko"] = "옛 본문"
    result, parts = t.translate_parts("New text.", "en", old, lambda *a: "새 본문", router())
    assert result == "새 본문" and parts[0]["text"] == "New text."
    assert old[0]["ko"] == "옛 본문"


@pytest.mark.parametrize("failure", ["exception", "timeout"])
def test_translation_failure_does_not_change_analysis_or_late_write(failure):
    release, started, finished = Event(), Event(), Event()

    def translate(*args):
        if failure == "exception":
            raise RuntimeError("translator unavailable")
        started.set()
        release.wait(2)
        finished.set()
        return "늦은 번역"

    baseline = service(lambda *a: None).submit(inquiry())
    svc = service(translate, router(inquiry_translation_timeout_s=0.02))
    begin = time.monotonic()
    try:
        result = svc.submit(inquiry())
        assert time.monotonic() - begin < 1
        for field in ("status", "category", "product_code", "priority", "assigned_dept", "draft"):
            assert getattr(result, field) == getattr(baseline, field)
        assert result.body_ko is None
    finally:
        release.set()
    if failure == "timeout":
        assert started.is_set() and finished.wait(1)
        assert svc.get(result.ticket_id).body_ko is None


def test_api_returns_translation_without_changing_customer_body():
    with TestClient(
        create_app(
            llm=router(),
            agents={**stubs.ANALYSIS, "translate": lambda *a: "제품 사양 문의"},
            storage="memory",
            retrievers=(None, None),
        )
    ) as client:
        response = client.post("/api/tickets", json=inquiry().model_dump(mode="json"))
        assert response.status_code == 201
        tid = response.json()["ticket_id"]
        assert client.get(f"/api/tickets/{tid}").json()["body_ko"] == "제품 사양 문의"
        assert client.app.state.tickets.records.tickets[tid]["body"] == inquiry().body


@needs_db
def test_postgres_translation_survives_restart_and_reuses_prior_parts(db):
    from sqlalchemy import text

    from cs_agent.db.models import Ticket
    from cs_agent.graph.builder import postgres_checkpointer
    from cs_agent.services.records import SqlRecords

    engine, Session = db
    calls = []

    def translate(body, language, llm):
        calls.append(body)
        return "한국어 번역: " + body

    try:
        with postgres_checkpointer(TEST_DATABASE_URL) as saver:
            svc = service(translate, checkpointer=saver, records=SqlRecords(Session))
            first = svc.submit(inquiry())

        with postgres_checkpointer(TEST_DATABASE_URL) as saver:
            restored = service(translate, checkpointer=saver, records=SqlRecords(Session))
            assert restored.get(first.ticket_id).body_ko == first.body_ko
            with Session() as session:
                row = session.get(Ticket, first.ticket_id)
                assert row.body == inquiry().body
                assert row.body_ko == first.body_ko

            result = restored.reply(first.ticket_id, inquiry("Also provide weight."))
            assert calls == [inquiry().body, "Also provide weight."]
            assert result.body_ko.count("한국어 번역:") == 2
            with Session() as session:
                row = session.get(Ticket, first.ticket_id)
                assert row.body_ko == result.body_ko
                assert "Also provide weight." in row.body
    finally:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "DROP TABLE IF EXISTS checkpoints, checkpoint_blobs, checkpoint_writes, "
                    "checkpoint_migrations"
                )
            )
