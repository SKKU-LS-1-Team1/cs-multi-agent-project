"""No live APIs: evidence, graph compatibility, customer isolation and durable vector indexing."""

import json
import time
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from stubs import ANALYSIS
from test_db import db as db
from test_db import needs_db

from cs_agent.agents.customer_followup import context, judge
from cs_agent.config import Settings
from cs_agent.db.models import EMBEDDING_DIM, InquiryHistoryChunk, Ticket
from cs_agent.domain import Category
from cs_agent.graph.builder import GraphDeps, build_ticket_graph
from cs_agent.llm.router import LLMRouter
from cs_agent.main import create_app
from cs_agent.schemas import CheckResult, Draft, InquiryIn, ReviewIn
from cs_agent.services.customer_history import (
    CustomerHistory,
    chunks_of,
    customer_source,
    sources_of,
)
from cs_agent.services.records import SqlRecords
from cs_agent.services.tickets import InvalidAction, TicketService

CURRENT = "After your firmware update advice in T-OLD, the same drive still trips."
PAST = "For the reported drive trip, please update the firmware."
CANDIDATES = [{"ticket_id": "T-OLD", "subject": "Drive trips", "sources": {"T-OLD/sent": PAST}}]


def output(**changes):
    return (
        dict(
            previous_ticket_id="T-OLD",
            relation="unresolved",
            reason="이전 업데이트 안내 후에도 트립이 지속됩니다.",
            new_information="업데이트 안내 후에도 같은 장비가 트립된다고 회신함",
            references=[
                {"source_id": "current", "quote": CURRENT},
                {"source_id": "T-OLD/sent", "quote": PAST},
            ],
        )
        | changes
    )


class LLM:
    enabled = True

    def __init__(self, result=None):
        self.result = result if result is not None else output()
        self.calls = []

    def write(self, task, prompt):
        self.calls.append((task, prompt))
        return json.dumps(self.result, ensure_ascii=False)


def test_judgement_preserves_evidence_and_context_is_not_technical_truth():
    llm = LLM()
    link = judge(CURRENT, CANDIDATES, llm)
    assert link["previous_ticket_id"] == "T-OLD"
    assert link["sources"]["T-OLD/sent"] == PAST
    assert "Advice sent does not mean" in context(link)
    assert context(link | {"dismissed": True}) == ""
    assert "Same customer/product/error" in llm.calls[0][1]


@pytest.mark.parametrize(
    "changes",
    [
        {"previous_ticket_id": "T-OTHER"},
        {"references": [{"source_id": "current", "quote": CURRENT}]},
        {"references": [{"source_id": "T-OLD/sent", "quote": PAST}]},
        {"references": [{"source_id": "current", "quote": "Invented quotation that is absent"}]},
    ],
)
def test_bad_ids_and_unverifiable_connections_are_rejected(changes):
    with pytest.raises(ValueError):
        judge(CURRENT, CANDIDATES, LLM(output(**changes)))


@pytest.mark.parametrize("relation", ["uncertain", "unrelated"])
def test_no_candidate_suggestions_are_returned(relation):
    assert (
        judge(CURRENT, CANDIDATES, LLM(output(relation=relation, previous_ticket_id=None))) is None
    )


def test_fake_and_oversized_inputs_never_create_links():
    fake = LLM()
    fake.enabled = False
    assert judge(CURRENT, CANDIDATES, fake) is None
    live = LLM()
    assert judge(CURRENT * 2000, CANDIDATES, live) is None
    assert not fake.calls and not live.calls


def test_index_contains_only_sent_answers_and_keeps_withdrawals():
    state = {
        "inquiry": {"subject": "Drive", "body": "Model corrected to S100"},
        "draft": Draft(text="UNSENT secret draft"),
        "processing_history": [{"kind": "sent", "text": PAST}, {"kind": "draft", "text": "UNSENT"}],
        "customer_messages": [{"body": "I withdraw the previous firmware version."}],
        "resolution": {"outcome": "unconfirmed"},
        "specialist_replies": [{"text": "Preliminary finding only"}],
    }
    sources = sources_of(state)
    assert "UNSENT" not in json.dumps(sources)
    assert sources["sent:0"] == PAST
    assert "withdraw" in sources["customer:0"]
    assert "unconfirmed" in sources["recorded_outcome"]
    text = "a" * 1700 + "Final correction: S100, not iS7"
    chunks = chunks_of({"customer": text})
    assert any("Final correction: S100, not iS7" in chunk for chunk in chunks.values())


def test_timeout_does_not_deliver_a_late_link():
    history = CustomerHistory(None, None, "test", None, LLM())

    def slow(*args):
        time.sleep(0.06)
        return CANDIDATES

    history.candidates = slow
    started = time.monotonic()
    assert (
        history.match(
            "T-NEW", InquiryIn(channel="email", customer_id="C", body=CURRENT), timeout=0.005
        )
        is None
    )
    assert time.monotonic() - started < 0.05
    time.sleep(0.08)  # Let the bounded worker finish; it has no mutation callback.


def test_form_values_are_searchable_customer_sources_without_inferred_fields():
    message = inquiry(provided_fields={"serial_no": "SN-17384", "current_fw": "2.10"})
    state = {
        "inquiry": message,
        "customer_messages": [TicketService._customer_message(message, "initial")],
        "extraction": {"serial_no": "MODEL-INFERRED-SERIAL"},
    }
    source = customer_source(message)
    assert CURRENT in source and "INV-LSLV0075-S100" in source
    assert "SN-17384" in source and "2.10" in source
    assert sources_of(state)["customer:0"] == source
    assert "MODEL-INFERRED-SERIAL" not in json.dumps(sources_of(state))


def test_match_passes_form_fields_and_rejects_a_checkpoint_changed_during_judgement():
    stamp = datetime.now(UTC)
    original = {"sent": PAST}
    current_sources = dict(original)
    llm = LLM()
    history = CustomerHistory(None, None, "test", None, llm)
    history.candidates = lambda *a: [CANDIDATES[0] | {"source_updated_at": stamp.isoformat()}]
    history.snapshot = lambda *a: ("C1", "Manual", stamp, dict(current_sources))
    message = inquiry(provided_fields={"serial_no": "SN-17384"})
    assert history.match("T-NEW", message)
    payload = json.loads(llm.calls[-1][1].rsplit("\n", 1)[-1])
    assert "SN-17384" in payload["current"]
    write = llm.write

    def changed(task, prompt):
        current_sources["sent"] = "The earlier answer was withdrawn."
        return write(task, prompt)

    llm.write = changed
    # DB timestamp has not changed yet; checkpoint content is already different.
    assert history.match("T-NEW", message) is None


def service(matcher):
    llm = LLMRouter(Settings(_env_file=None))
    deps = GraphDeps(
        llm=llm,
        **ANALYSIS,
        write_draft=lambda *a, **kw: Draft(
            text="Please see the manual", slots={"draft_language": "en"}
        ),
        verify=lambda *a, **kw: [CheckResult(name="test", passed=True)],
    )
    return TicketService(build_ticket_graph(deps), history_matcher=matcher)


def inquiry(**changes):
    return InquiryIn(
        channel="email",
        customer_id="C1",
        subject="Manual",
        body=CURRENT,
        category="MANUAL",
        product_code="INV-LSLV0075-S100",
        language="en",
        **changes,
    )


def test_link_does_not_overwrite_ticket_or_thread_reply_and_unlink_survives():
    calls = []
    link = judge(CURRENT, CANDIDATES, LLM())

    def match(*args):
        calls.append(args)
        return link

    svc = service(match)
    row = svc.submit(inquiry(thread_ref="thread-one"))
    assert row.followup_link == link and row.inquiry.body == CURRENT
    assert row.status == "READY_FOR_REVIEW"
    assert row.draft is not None
    detached = svc.unlink_followup(row.ticket_id)
    assert detached.followup_link["dismissed"] and detached.followup_context_stale
    with pytest.raises(InvalidAction, match="재작성"):
        svc.act(row.ticket_id, ReviewIn(action="approve"))
    with pytest.raises(InvalidAction, match="재작성"):
        svc.prepare_reply(row.ticket_id, row.draft.text, None)
    # Unlink is idempotent and stays detached when a real thread reply is processed.
    svc.unlink_followup(row.ticket_id)
    reply = svc.submit(inquiry(thread_ref="thread-one"))
    assert reply.ticket_id == row.ticket_id
    assert reply.followup_link["dismissed"]
    assert len(calls) == 1
    assert svc.records.tickets[row.ticket_id]["followup_link"]["dismissed"]


def test_failure_does_not_prevent_existing_analysis():
    def unavailable(*args):
        raise TimeoutError()

    row = service(unavailable).submit(inquiry())
    assert row.followup_link is None
    assert row.category == "MANUAL" and row.status == "READY_FOR_REVIEW"


def test_public_cannot_select_another_demo_customers_history():
    with TestClient(
        create_app(
            llm=LLMRouter(Settings(_env_file=None)),
            agents=ANALYSIS,
            storage="memory",
            retrievers=(None, None),
        )
    ) as client:
        calls = []
        client.app.state.tickets.history_matcher = lambda *args: calls.append(args)
        response = client.post("/api/inquiries", json=inquiry().model_dump(mode="json"))
        assert response.status_code == 400
        assert calls == []


class Embed:
    def __init__(self):
        self.calls = []

    def __call__(self, texts):
        self.calls.extend(texts)
        return [[1.0] + [0.0] * (EMBEDDING_DIM - 1) for _ in texts]


@needs_db
def test_vector_index_reuses_vectors_scopes_customers_and_preserves_originals(db):
    _, Session = db
    records = SqlRecords(Session)
    older = datetime.now(UTC) - timedelta(days=1)
    for ticket_id, customer in [("T-OLD", "C1"), ("T-OTHER", "C2")]:
        records.add_ticket(
            ticket_id,
            InquiryIn(channel="email", customer_id=customer, body=PAST, received_at=older),
        )
    embed = Embed()
    history = CustomerHistory(Session, embed, "test-model", lambda _: {}, LLM())
    assert history.refresh("T-OLD")
    calls = len(embed.calls)
    assert history.refresh("T-OLD") and len(embed.calls) == calls
    history.refresh("T-OTHER")
    candidates = history.candidates("T-NEW", inquiry())
    assert [c["ticket_id"] for c in candidates] == ["T-OLD"]
    assert history.candidates("T-OLD", inquiry()) == []
    assert history.candidates("T-NEW", inquiry().model_copy(update={"customer_id": None})) == []
    with Session.begin() as s:
        row = s.get(Ticket, "T-OLD")
        assert row.status == "NEW" and row.resolution is None and row.body == PAST
        row.body = "Correction: the device is S100 and there is no fire."
    history.refresh("T-OLD")
    with Session() as s:
        chunks = s.scalars(
            select(InquiryHistoryChunk).where(InquiryHistoryChunk.ticket_id == "T-OLD")
        ).all()
        assert len(chunks) == 1 and "Correction:" in chunks[0].text
        assert s.scalar(select(func.count()).select_from(Ticket)) == 2
    # Model changes invalidate vectors rather than silently mixing embedding spaces.
    history.version = "history-v1:another-model:1536"
    assert history.candidates("T-NEW", inquiry()) != []  # Explicit ID still works without a vector.
    plain = inquiry().model_copy(update={"body": "The drive still trips"})
    assert history.candidates("T-NEW", plain) == []
    before = len(embed.calls)
    history.refresh("T-OLD")
    assert len(embed.calls) > before


@needs_db
def test_embedding_failure_keeps_previous_index_and_ticket(db):
    _, Session = db
    records = SqlRecords(Session)
    records.add_ticket("T-OLD", inquiry())
    history = CustomerHistory(Session, Embed(), "model", lambda _: {}, LLM())
    history.refresh("T-OLD")
    with Session.begin() as s:
        s.get(Ticket, "T-OLD").body = "New customer correction"

    def fail(_):
        raise TimeoutError()

    history.embed = fail
    with pytest.raises(TimeoutError):
        history.refresh("T-OLD")
    with Session() as s:
        assert s.get(Ticket, "T-OLD").body == "New customer correction"
        assert CURRENT in s.scalar(select(InquiryHistoryChunk.text))


def test_draft_prompt_receives_history_separately_from_technical_evidence():
    from test_drafting import Writer, extraction, router

    from cs_agent.agents.drafting import write_draft
    from cs_agent.domain import Category

    writer = Writer()
    write_draft(
        Category.MANUAL,
        extraction(Category.MANUAL),
        [],
        CURRENT,
        router(writer),
        followup_link=judge(CURRENT, CANDIDATES, LLM()),
    )
    payload = writer.contexts[0]
    assert PAST in payload["historical_followup_context"]
    assert "T-OLD" not in payload["allowed_citations"]
    assert not any("T-OLD" in str(d) for d in payload["official_documents"])


def test_unlinked_draft_can_be_regenerated_and_preview_context_changes():
    from cs_agent.services.reply_preview import context_key

    link = judge(CURRENT, CANDIDATES, LLM())
    svc = service(lambda *args: link)
    row = svc.submit(inquiry())
    before = context_key(svc._state(row.ticket_id).values)
    svc.unlink_followup(row.ticket_id)
    assert before != context_key(svc._state(row.ticket_id).values)
    regenerated = svc.act(row.ticket_id, ReviewIn(action="rewrite", draft_purpose="answer"))
    assert regenerated.followup_link["dismissed"]
    assert not regenerated.followup_context_stale
    assert regenerated.draft is not None


@needs_db
def test_followup_relationship_survives_checkpoint_restore_without_reclassifying(db):
    from test_db import TEST_DATABASE_URL, _db_service

    from cs_agent.graph.builder import postgres_checkpointer

    _, Session = db
    link = judge(CURRENT, CANDIDATES, LLM())
    with postgres_checkpointer(TEST_DATABASE_URL) as saver:
        svc = _db_service(Session, saver)
        svc.history_matcher = lambda *args: link
        row = svc.submit(inquiry())
        tid = row.ticket_id
        assert svc.get(tid).followup_link == link
    with postgres_checkpointer(TEST_DATABASE_URL) as saver:
        restored = _db_service(Session, saver)
        assert restored.get(tid).followup_link == link
        restored.unlink_followup(tid)
        with Session() as s:
            assert s.get(Ticket, tid).followup_link["dismissed"]
    with postgres_checkpointer(TEST_DATABASE_URL) as saver:
        assert _db_service(Session, saver).get(tid).followup_link["dismissed"]


def test_escalation_prompt_keeps_history_separate_from_official_documents():
    from test_escalation import Writer
    from test_escalation import state as state_fixture

    from cs_agent.agents.escalation import write_escalation_request

    state = state_fixture.__wrapped__()
    state["followup_link"] = judge(CURRENT, CANDIDATES, LLM())
    writer = Writer()
    write_escalation_request(state, llm=LLMRouter(Settings(_env_file=None), writer=writer))
    assert "historical_followup_context" in writer.prompts[0]
    assert PAST in writer.prompts[0]


def test_previous_response_requires_sent_or_outcome_evidence():
    sent_candidates = [
        {
            "ticket_id": "T-OLD",
            "subject": "Previous",
            "sources": {
                "T-OLD/sent:0": PAST,
                "T-OLD/customer:0": "Can you send the manual please?",
            },
        }
    ]
    result = output(
        references=[
            {"source_id": "current", "quote": CURRENT},
            {"source_id": "T-OLD/sent:0", "quote": PAST},
        ],
        previous_response={
            "text": "펌웨어 업데이트를 안내했습니다.",
            "references": [{"source_id": "T-OLD/sent:0", "quote": PAST}],
        },
    )
    link = judge(CURRENT, sent_candidates, LLM(result))
    assert link["previous_response"]["text"] == "펌웨어 업데이트를 안내했습니다."
    assert link["current_source"] == CURRENT
    result["previous_response"]["references"] = [
        {"source_id": "T-OLD/customer:0", "quote": "Can you send the manual please?"}
    ]
    with pytest.raises(ValueError, match="sent answer"):
        judge(CURRENT, sent_candidates, LLM(result))


@pytest.mark.parametrize("supplied_id", [None, "CUST-0557"])
def test_web_form_profile_reaches_matcher_and_internal_evidence_stays_admin_only(supplied_id):
    with TestClient(
        create_app(
            llm=LLMRouter(Settings(_env_file=None)),
            agents=ANALYSIS,
            storage="memory",
            retrievers=(None, None),
        )
    ) as client:
        calls = []
        link = judge(CURRENT, CANDIDATES, LLM())

        def match(ticket_id, message):
            calls.append((ticket_id, message.customer_id))
            return link

        client.app.state.tickets.history_matcher = match
        payload = inquiry().model_dump(mode="json") | {"customer_id": supplied_id}
        result = client.post("/api/inquiries", json=payload)
        assert result.status_code == 201, result.text
        tid = result.json()["ticket_id"]
        assert calls == [(tid, "CUST-0557")]
        assert "followup_link" not in result.json() and result.json()["message"] is None
        detail = client.get(f"/api/tickets/{tid}").json()
        assert detail["inquiry"]["customer_id"] == "CUST-0557"
        assert detail["followup_link"]["previous_ticket_id"] == "T-OLD"
        assert detail["followup_link"]["references"][0]["quote"] == CURRENT
        assert detail["inquiry"]["body"] == CURRENT


@pytest.mark.parametrize(
    "category,body",
    [
        ("MANUAL", "Please send the S100 manual."),
        ("DEFECT", "The drive stopped working. I don't have a serial number."),
        ("DEFECT", "Smoke is coming from the S100."),
    ],
)
def test_link_does_not_override_existing_information_answer_or_human_routes(category, body):
    message = inquiry().model_copy(update={"category": Category(category), "body": body})
    baseline = service(None).submit(message)
    linked = service(lambda *args: judge(CURRENT, CANDIDATES, LLM())).submit(message)
    assert (linked.status, linked.route, linked.category) == (
        baseline.status,
        baseline.route,
        baseline.category,
    )
    assert bool(linked.draft) == bool(baseline.draft)
    assert bool(linked.info_request) == bool(baseline.info_request)


@needs_db
def test_web_submit_vector_search_admin_display_direct_reply_and_unlink_end_to_end(db):
    """Public intake → real pgvector query → validated judgement → normal graph → admin API."""
    import copy

    from cs_agent.domain import ReviewAction

    _, Session = db
    agents = {
        **ANALYSIS,
        "write_draft": lambda *a, **k: Draft(text=PAST, slots={"draft_language": "en"}),
        "verify": lambda *a, **k: [CheckResult(name="test", passed=True)],
    }
    with TestClient(
        create_app(
            llm=LLMRouter(Settings(_env_file=None)),
            agents=agents,
            storage="memory",
            retrievers=(None, None),
        )
    ) as client:
        svc = client.app.state.tickets
        svc.records = SqlRecords(Session)
        parent = svc.submit(
            inquiry().model_copy(update={"customer_id": "CUST-0557", "body": "The drive trips."})
        )
        svc.act(parent.ticket_id, ReviewIn(action=ReviewAction.APPROVE))
        svc.resolve(parent.ticket_id)
        before = copy.deepcopy(svc._state(parent.ticket_id).values)
        history = CustomerHistory(
            Session, Embed(), "test-model", lambda tid: svc._state(tid).values, LLM()
        )
        assert history.refresh(parent.ticket_id)
        seen = []

        class ReadingLLM:
            enabled = True

            def write(self, task, prompt):
                payload = json.loads(prompt[prompt.index('\n{"current"') + 1 :])
                seen.append(payload)
                candidate = payload["candidates"][0]
                assert candidate["ticket_id"] == parent.ticket_id
                sent_id = next(k for k in candidate["sources"] if "/sent:" in k)
                quote = candidate["sources"][sent_id]
                return json.dumps(
                    output(
                        previous_ticket_id=parent.ticket_id,
                        references=[
                            {"source_id": "current", "quote": CURRENT},
                            {"source_id": sent_id, "quote": quote},
                        ],
                        previous_response={
                            "text": "펌웨어 업데이트를 안내했습니다.",
                            "references": [{"source_id": sent_id, "quote": quote}],
                        },
                    )
                )

        history.llm = ReadingLLM()
        svc.history_matcher = history.match
        payload = inquiry(thread_ref="web-followup-new").model_dump(mode="json") | {
            "customer_id": "CUST-0557"
        }
        result = client.post("/api/inquiries", json=payload)
        assert result.status_code == 201, result.text
        tid = result.json()["ticket_id"]
        assert tid != parent.ticket_id and len(seen) == 1
        detail = client.get(f"/api/tickets/{tid}").json()
        assert detail["followup_link"]["previous_ticket_id"] == parent.ticket_id
        assert detail["followup_link"]["previous_response"]["text"]
        assert detail["status"] == "READY_FOR_REVIEW"
        assert svc._state(tid).values["followups"] == 0
        assert svc._state(parent.ticket_id).values == before
        # Explicit same-thread reply remains on the new ticket, without another match call.
        reply = client.post(
            "/api/inquiries", json=payload | {"body": "One more detail: it stops after 3 seconds."}
        )
        assert reply.status_code == 201 and reply.json()["ticket_id"] == tid
        assert svc._state(tid).values["followups"] == 1 and len(seen) == 1
        detached = client.post(f"/api/tickets/{tid}/followup/unlink")
        assert detached.status_code == 200 and detached.json()["followup_link"]["dismissed"]
        assert client.get(f"/api/tickets/{tid}").json()["followup_link"]["dismissed"]
        with Session() as s:
            assert s.get(Ticket, parent.ticket_id).status == "RESOLVED"
            assert s.get(Ticket, tid).customer_id == "CUST-0557"
