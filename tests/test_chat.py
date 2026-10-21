import pytest
from fastapi.testclient import TestClient

from cs_agent.agents.analysis import AnalysisError
from cs_agent.chatbot import agent
from cs_agent.chatbot.agent import ChatIn, respond
from cs_agent.config import Settings
from cs_agent.domain import Category
from cs_agent.llm.clients import Completion, Judgement
from cs_agent.llm.router import LLMRouter
from cs_agent.main import create_app
from cs_agent.rules.tables import load_tables
from cs_agent.schemas import Classification, Evidence, Extraction

TABLES = load_tables()
S100 = "INV-LSLV0075-S100"

# 챗봇 기록: 고객 / 챗봇 답변 순서로 번갈아 쌓인다 (api/chat.py)
ADVICE = "가속 시간(F23)을 늘려 보세요."


class ScriptedWriter:
    name = "gemini-writer"

    def __init__(self, *outputs, default="ANSWER"):
        self.outputs = list(outputs)
        self.default = default
        self.prompts: list[str] = []

    def write(self, prompt):
        self.prompts.append(prompt)
        out = self.outputs.pop(0) if self.outputs else self.default
        if isinstance(out, Exception):
            raise out
        return Completion(out, self.name)


class IntentJudge:
    """고객 말에 들어 있는 낱말로 의도를 돌려준다."""

    name = "jev"

    def __init__(self):
        self.calls: list[str] = []

    def judge(self, prompt, options):
        message = prompt.rsplit("Customer's latest message:\n", 1)[1]
        self.calls.append(message.strip())
        if "AGAIN" in message:
            return Judgement("RECURRENCE", 0.95, self.name)
        if "AGENT" in message:
            return Judgement("REQUEST_AGENT", 0.95, self.name)
        return Judgement("OTHER", 0.95, self.name)


class FakeDocs:
    """검색 호출을 기록하고 정해 둔 근거를 돌려준다."""

    def __init__(self, evidence):
        self.evidence = evidence
        self.calls: list[tuple[str, int, dict | None]] = []

    def search(self, query, k=5, where=None):
        self.calls.append((query, k, where))
        return list(self.evidence)[:k]


def tg(score=0.82, product=S100, doc_id="TG-S100"):
    return Evidence(
        source="docs",
        doc_id=doc_id,
        section="3.1 E.OC",
        text="E.OC: overcurrent during acceleration. Increase acceleration time (F23).",
        score=score,
        metadata={"doc_type": "TG", "product_code": product, "family": "DRIVE", "title": "E.OC"},
    )


def live(writer=None, judge=None, **kw) -> LLMRouter:
    return LLMRouter(
        Settings(_env_file=None, llm_provider="live"),
        jev=judge or IntentJudge(),
        writer=writer or ScriptedWriter(),
        **kw,
    )


@pytest.fixture
def analysis(monkeypatch):
    """분석을 고정한다 (분류·추출 자체는 test_analysis.py 에서 본다)."""
    state = {
        "classification": Classification(category=Category.DEFECT, confidence=0.9),
        "extraction": Extraction(
            product_code=S100, product_family="DRIVE", error_code="E.OC", language="ko"
        ),
        "calls": [],
    }

    def fake_classify(inquiry, llm, **kw):
        state["calls"].append(("classify", inquiry, kw))
        if isinstance(state["classification"], Exception):
            raise state["classification"]
        return state["classification"]

    def fake_extract(inquiry, tables, **kw):
        state["calls"].append(("extract", inquiry, kw))
        return state["extraction"]

    monkeypatch.setattr(agent, "classify", fake_classify)
    monkeypatch.setattr(agent, "extract", fake_extract)
    return state


def say(message="S100 가속 중 E.OC", **kw) -> ChatIn:
    return ChatIn(session_id="s1", message=message, language="ko", **kw)


# 기획서 5.4 · 5.5 시나리오: S100 E.OC → 고장 탭 → 재발 → 문의하기


def test_defect_question_moves_dashboard_and_answers_from_evidence(analysis):
    writer = ScriptedWriter("E.OC 는 가속 중 과전류입니다. F23 을 늘려 보세요.")
    docs = FakeDocs([tg()])

    out = respond(say(), [], docs, live(writer), TABLES)

    assert out.answer == "E.OC 는 가속 중 과전류입니다. F23 을 늘려 보세요."
    assert (out.navigation.product_code, out.navigation.tab, out.navigation.anchor) == (
        S100,
        "faults",
        "E.OC",
    )
    assert [e.doc_id for e in out.evidence] == ["TG-S100"]
    assert out.handoff is False and out.form is None
    prompt = writer.prompts[0]
    assert "Increase acceleration time (F23)" in prompt  # 근거 문서
    assert "[TG-S100 · 3.1 E.OC]" in prompt
    assert "LSLV S100 7.5kW VFD" in prompt


def test_answer_prompt_forbids_deciding_and_uses_customer_language(analysis):
    writer = ScriptedWriter()

    respond(say(), [], FakeDocs([tg()]), live(writer), TABLES)

    prompt = writer.prompts[0]
    assert "in ko" in prompt  # 추출된 언어
    assert "Never confirm a quotation amount" in prompt
    assert "ONLY the reference documents" in prompt


def test_recurrence_after_remote_advice_hands_off_with_prefilled_form(analysis):
    history = [
        "S100 가속 중 E.OC",
        ADVICE,
        "STILL AGAIN E.OC",  # 재발 1
        ADVICE,
    ]
    writer = ScriptedWriter(
        "Repeated E.OC\n\nWe already increased the acceleration time.",
        "같은 문제가 다시 생겨 문의서로 이동합니다.",  # 전환 안내 번역
    )

    out = respond(say("E.OC AGAIN"), history, FakeDocs([tg()]), live(writer), TABLES)  # 재발 2

    assert out.handoff is True
    assert "same problem came back" in out.handoff_reason
    assert out.form is not None
    assert out.form.category == "DEFECT"
    assert out.form.product_code == S100
    assert out.form.fields["error_code"] == "E.OC"
    assert out.form.subject == "Repeated E.OC"
    assert out.answer == "같은 문제가 다시 생겨 문의서로 이동합니다."
    assert out.handoff_reason in writer.prompts[1]  # 번역 요청에 전환 이유가 들어간다


def test_single_recurrence_is_not_enough(analysis):
    history = ["S100 가속 중 E.OC", ADVICE]

    out = respond(say("E.OC AGAIN"), history, FakeDocs([tg()]), live(), TABLES)

    assert out.handoff is False


def test_unresolved_button_hands_off_immediately(analysis):
    writer = ScriptedWriter("Subject line\n\nBody text")

    out = respond(
        say("해결 안 됐어요", unresolved=True), [], FakeDocs([tg()]), live(writer), TABLES
    )

    assert out.handoff is True
    assert out.form is not None
    assert "wasn't resolved" in out.handoff_reason


def test_customer_asking_for_an_agent_hands_off(analysis):
    out = respond(say("connect me to an AGENT"), [], FakeDocs([tg()]), live(), TABLES)

    assert out.handoff is True
    assert "wasn't resolved" in out.handoff_reason


def test_decision_categories_hand_off(analysis):
    analysis["classification"] = Classification(category=Category.QUOTE, confidence=0.9)

    out = respond(say("PCS 100kW 20대 견적"), [], FakeDocs([tg()]), live(), TABLES)

    assert out.handoff is True
    assert "quotation" in out.handoff_reason
    assert out.form.category == "QUOTE"


@pytest.mark.parametrize("docs", [None, FakeDocs([])])
def test_no_evidence_hands_off(analysis, docs):
    out = respond(say(), [], docs, live(), TABLES)

    assert out.handoff is True
    assert "couldn't find this" in out.handoff_reason


def test_weak_evidence_hands_off(analysis):
    out = respond(say(), [], FakeDocs([tg(score=0.5)]), live(), TABLES)

    assert out.handoff is True


# 검색 · 점수


def test_best_score_search_is_unfiltered_and_uses_recent_customer_messages(analysis):
    docs = FakeDocs([tg()])
    history = ["m1", "a1", "m2", "a2", "m3", "a3"]

    respond(say("m4"), history, docs, live(), TABLES)

    query, k, where = docs.calls[0]
    assert (k, where) == (1, None)  # 제품 필터 없이 1등 (handoff 기준값을 그렇게 쟀다)
    assert query == "m2\nm3\nm4"


def test_evidence_of_other_products_is_dropped_but_does_not_lower_the_score(analysis):
    docs = FakeDocs([tg(0.9, product="INV-LSLV0220-H100", doc_id="TG-H100"), tg(0.8)])

    out = respond(say(), [], docs, live(), TABLES)

    assert out.handoff is False
    assert [e.metadata["product_code"] for e in out.evidence] == [S100]


# 분석


def test_history_is_passed_to_analysis_with_roles(analysis):
    history = ["첫 질문", "첫 답", "둘째 질문", "둘째 답"]

    respond(say("셋째"), history, FakeDocs([tg()]), live(), TABLES)

    kind, inquiry, kw = analysis["calls"][0]
    assert inquiry.body == "셋째" and inquiry.channel == "CHAT"
    assert [m["role"] for m in kw["transcript"]] == ["user", "assistant", "user", "assistant"]
    assert kw["transcript"][2]["content"] == "둘째 질문"


def test_odd_length_history_is_realigned_to_start_with_customer(analysis):
    history = ["(잘린 답변)", "고객1", "답1"]

    respond(say("고객2"), history, FakeDocs([tg()]), live(), TABLES)

    transcript = analysis["calls"][0][2]["transcript"]
    assert [(m["role"], m["content"]) for m in transcript] == [
        ("user", "고객1"),
        ("assistant", "답1"),
    ]


def test_extraction_gets_the_category_found_by_classification(analysis):
    respond(say(), [], FakeDocs([tg()]), live(), TABLES)

    assert analysis["calls"][1][2]["category"] == Category.DEFECT


def test_viewed_product_becomes_the_context_when_message_names_none(analysis):
    analysis["extraction"] = Extraction()
    analysis["classification"] = Classification(category=Category.TECH_SPEC, confidence=0.9)

    out = respond(
        say("차단 용량은?", viewing_product="ACB-AS-2000"), [], FakeDocs([tg()]), live(), TABLES
    )

    kind, inquiry, kw = analysis["calls"][0]
    assert inquiry.product_code == "ACB-AS-2000"
    assert out.navigation.product_code == "ACB-AS-2000"


def test_unknown_viewed_product_is_ignored(analysis):
    analysis["extraction"] = Extraction()
    analysis["classification"] = None
    analysis["classification"] = Classification(category=Category.TECH_SPEC, confidence=0.9)

    respond(say(viewing_product="NOPE"), [], FakeDocs([tg()]), live(), TABLES)

    assert analysis["calls"][0][1].product_code is None


def test_analysis_failure_keeps_chatting_without_moving_the_dashboard(analysis):
    analysis["classification"] = AnalysisError("classification_failed")

    out = respond(say("가속 중 에러", viewing_product=S100), [], FakeDocs([tg()]), live(), TABLES)

    assert out.navigation.product_code is None and out.navigation.tab is None
    assert out.handoff is False
    assert out.answer == "ANSWER"


def test_analysis_failure_with_handoff_has_no_form(analysis):
    analysis["classification"] = AnalysisError("classification_failed")

    out = respond(say(unresolved=True), [], FakeDocs([tg()]), live(), TABLES)

    assert out.handoff is True and out.form is None


# ask_fields


def test_ask_fields_are_missing_required_items_blocking_first(analysis):
    out = respond(say(), [], FakeDocs([tg()]), live(), TABLES)

    # DRIVE · DEFECT: 필수 product_model, serial_no, error_code, operating_condition, …
    # 차단 항목은 serial_no · error_code. 제품과 에러코드는 이미 나왔다
    assert out.ask_fields == ["serial_no", "operating_condition"]


def test_ask_fields_skip_provided_values_and_cap_at_two(analysis):
    analysis["extraction"] = analysis["extraction"].model_copy(
        update={"provided_info": ["serial_no"], "field_values": {"operating_condition": "x"}}
    )

    out = respond(say(), [], FakeDocs([tg()]), live(), TABLES)

    assert out.ask_fields == ["photos", "logs"]


def test_no_ask_fields_without_category(analysis):
    analysis["classification"] = AnalysisError("x")

    out = respond(say(), [], FakeDocs([tg()]), live(), TABLES)

    assert out.ask_fields == []


# 판단 모델이 없을 때


def test_judge_off_means_no_handoff_signal_from_conversation(analysis):
    llm = LLMRouter(Settings(_env_file=None), writer=ScriptedWriter())
    history = ["m1", ADVICE, "AGAIN", ADVICE]

    out = respond(say("AGAIN AGENT"), history, FakeDocs([tg()]), llm, TABLES)

    assert out.handoff is False


def test_intent_is_only_rechecked_for_diagnosis_categories(analysis):
    analysis["classification"] = Classification(category=Category.TECH_SPEC, confidence=0.9)
    judge = IntentJudge()
    history = ["m1", "a1", "m2", "a2"]

    respond(say("m3"), history, FakeDocs([tg()]), live(judge=judge), TABLES)

    assert judge.calls == ["m3"]  # 지난 말은 다시 판단하지 않는다


def test_intent_judgement_failure_is_treated_as_nothing_happened(analysis):
    class Broken:
        name = "jev"

        def judge(self, prompt, options):
            raise RuntimeError("down")

    out = respond(say(), [], FakeDocs([tg()]), live(judge=Broken()), TABLES)

    assert out.handoff is False


# 전환 안내 문장


def test_handoff_answer_is_translated_to_the_customer_language(analysis):
    writer = ScriptedWriter(
        "Subject\n\nBody", "해결되지 않아 문의하기로 넘깁니다."
    )  # 문의서 요약, 번역 순서

    out = respond(say(unresolved=True), [], FakeDocs([tg()]), live(writer), TABLES)

    assert out.answer == "해결되지 않아 문의하기로 넘깁니다."
    assert "Translate the text into ko" in writer.prompts[1]


def test_handoff_answer_falls_back_to_english_when_translation_fails(analysis):
    writer = ScriptedWriter("Subject\n\nBody", RuntimeError("boom"))  # 문의서 요약, 번역 순서

    out = respond(say(unresolved=True), [], FakeDocs([tg()]), live(writer), TABLES)

    assert out.answer.startswith("Since this wasn't resolved")
    assert out.answer.endswith("what we've discussed so far.")


def test_english_customers_get_the_english_text_without_a_model_call(analysis):
    analysis["extraction"] = analysis["extraction"].model_copy(update={"language": "en"})
    writer = ScriptedWriter("Subject\n\nBody")

    out = respond(say(unresolved=True), [], FakeDocs([tg()]), live(writer), TABLES)

    assert out.answer.startswith("Since this wasn't resolved")
    assert len(writer.prompts) == 1  # 문의서 요약 한 번뿐


# API


@pytest.fixture
def client(analysis):
    writer = ScriptedWriter(default="안내입니다.")
    app = create_app(llm=live(writer), storage="memory", retrievers=(FakeDocs([tg()]), None))
    with TestClient(app) as c:
        c.writer = writer
        yield c


def test_chat_endpoint_remembers_the_conversation(client, analysis):
    first = client.post(
        "/api/chat", json={"session_id": "abc", "message": "S100 E.OC", "language": "ko"}
    )
    assert first.status_code == 200
    body = first.json()
    assert body["answer"] == "안내입니다."
    assert body["navigation"]["tab"] == "faults"
    assert body["handoff"] is False

    client.post("/api/chat", json={"session_id": "abc", "message": "그래도 같아요"})

    assert client.app.state.chat_sessions.history("abc") == [
        "S100 E.OC",
        "안내입니다.",
        "그래도 같아요",
        "안내입니다.",
    ]
    second_call = analysis["calls"][2]  # 두 번째 요청의 classify
    assert [m["content"] for m in second_call[2]["transcript"]] == ["S100 E.OC", "안내입니다."]


def test_sessions_are_separate(client):
    client.post("/api/chat", json={"session_id": "a", "message": "one"})
    client.post("/api/chat", json={"session_id": "b", "message": "two"})

    sessions = client.app.state.chat_sessions
    assert sessions.history("a")[0] == "one" and sessions.history("b")[0] == "two"


def test_rate_limit_returns_429_and_keeps_history_clean(client, monkeypatch):
    from cs_agent.llm.router import RateLimited

    def limited(*args, **kwargs):
        raise RateLimited("gemini 분당 60회 초과")

    monkeypatch.setattr("cs_agent.api.chat.respond", limited)

    res = client.post("/api/chat", json={"session_id": "r", "message": "hi"})

    assert res.status_code == 429
    assert client.app.state.chat_sessions.history("r") == []


def test_chat_response_has_the_shape_the_screen_expects(client):
    body = client.post("/api/chat", json={"session_id": "x", "message": "hi"}).json()

    assert set(body) == {
        "answer",
        "navigation",
        "evidence",
        "ask_fields",
        "handoff",
        "handoff_reason",
        "form",
    }
    assert set(body["navigation"]) == {"product_code", "tab", "anchor", "rule_id", "candidates"}
