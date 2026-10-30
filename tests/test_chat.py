import pytest
from fastapi.testclient import TestClient

from cs_agent.agents.analysis import AnalysisError
from cs_agent.chatbot import agent
from cs_agent.chatbot.agent import DECLINE_ANSWER, ChatIn, respond
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
# 고객 언어로 확인되는 전환 안내 번역 (info_request.in_language: 글자 20자 이상)
HANDOFF_KO = (
    "같은 문제가 다시 생겨서 담당 엔지니어가 확인해야 합니다. "
    "지금까지 나눈 내용으로 문의서를 열어 드릴게요."
)


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
        if "Our products:\n" in prompt:  # 우리 제품 이야기인지 (OUR_PRODUCT_PROMPT)
            message = prompt.rsplit("(latest last):\n", 1)[1]
            self.calls.append(("our_product", message.strip()))
            return Judgement("YES" if "인터버" in message else "NO", 0.95, self.name)
        if "Customer's message:\n" in prompt:  # 결정 필요 판단 (DECISION_PROMPT)
            message = prompt.rsplit("Customer's message:\n", 1)[1]
            self.calls.append(("decision", message.strip()))
            return Judgement("INFO" if "INFO" in message else "DECISION", 0.95, self.name)
        message = prompt.rsplit("Customer's latest message:\n", 1)[1]
        self.calls.append(message.strip())
        if "AGAIN" in message:
            return Judgement("RECURRENCE", 0.95, self.name)
        if "AGENT" in message:
            return Judgement("REQUEST_AGENT", 0.95, self.name)
        if "궁금" in message:
            return Judgement("GENERAL", 0.95, self.name)
        return Judgement("OTHER", 0.95, self.name)


class FakeDocs:
    """검색 호출을 기록하고 정해 둔 근거를 돌려준다."""

    calibrated = True  # pgvector 처럼 점수를 기준값과 비교한다

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


def say(message="S100 가속 중 E.OC", language="ko", **kw) -> ChatIn:
    return ChatIn(session_id="s1", message=message, language=language, **kw)


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
    assert "in Korean" in prompt  # 고객 언어
    assert "Never confirm a quotation amount" in prompt
    assert "ONLY the reference documents" in prompt


def test_answer_is_formatted_for_the_chat_window(analysis):
    writer = ScriptedWriter(
        "## 답변\nE.OC 는 **가속 중 과전류**입니다.\n\n"
        "* 가속 시간 `F23` 을 늘려 보세요. [TG-S100 · 3.1 E.OC]\n"
        "* *부하*를 확인하세요.\n\n\n\n1. 다시 운전해 보세요."
    )

    out = respond(say(), [], FakeDocs([tg()]), live(writer), TABLES)

    prompt = writer.prompts[0]
    assert "Format for a narrow chat window" in prompt
    assert "[TG-S100 · 3.1 E.OC]" in prompt  # 답변에 그대로 다는 근거 이름
    assert DECLINE_ANSWER["ko"] in prompt  # 대화 중 엉뚱한 말에도 같은 안내
    # 화면이 그리는 굵게 · 목록 · [문서 · 절] 만 남고 제목 · 코드 · 기울임은 걷힌다
    assert out.answer == (
        "답변\nE.OC 는 **가속 중 과전류**입니다.\n\n"
        "- 가속 시간 F23 을 늘려 보세요. [TG-S100 · 3.1 E.OC]\n"
        "- 부하를 확인하세요.\n\n1. 다시 운전해 보세요."
    )


def test_recurrence_after_remote_advice_hands_off_with_prefilled_form(analysis):
    history = [
        "S100 가속 중 E.OC",
        ADVICE,
        "STILL AGAIN E.OC",  # 재발 1
        ADVICE,
    ]
    writer = ScriptedWriter(
        HANDOFF_KO,  # 전환 안내 번역 (추출을 기다리는 동안 먼저)
        "Repeated E.OC\n\nWe already increased the acceleration time.",
    )

    out = respond(say("E.OC AGAIN"), history, FakeDocs([tg()]), live(writer), TABLES)  # 재발 2

    assert out.handoff is True
    assert "same problem came back" in out.handoff_reason
    assert out.form is not None
    assert out.form.category == "DEFECT"
    assert out.form.product_code == S100
    assert out.form.fields["error_code"] == "E.OC"
    assert out.form.subject == "Repeated E.OC"
    assert out.answer == HANDOFF_KO
    assert out.handoff_reason in writer.prompts[0]  # 번역 요청에 전환 이유가 들어간다


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


OUT_OF_SCOPE = "오늘 서울 날씨 어때요?"  # 제품·제품군·에러코드가 없는 말


@pytest.mark.parametrize("docs", [None, FakeDocs([]), FakeDocs([tg(score=0.5)])])
def test_out_of_scope_question_is_declined_not_handed_off(analysis, docs):
    judge, writer = IntentJudge(), ScriptedWriter()

    out = respond(say(OUT_OF_SCOPE), [], docs, live(writer, judge), TABLES)

    assert ("our_product", OUT_OF_SCOPE) in judge.calls  # Jev 가 우리 제품이 아니라고 함
    assert out.handoff is False and out.form is None
    assert out.answer == DECLINE_ANSWER["ko"]
    assert "문의주신 정보는 제공되지 않습니다" in out.answer
    assert out.navigation.product_code is None
    assert writer.prompts == []  # 답변을 쓰지 않는다


def test_decline_follows_customer_language(analysis):
    out = respond(say("What's the weather in Seoul?", language="en"), [], None, live(), TABLES)
    assert out.answer == DECLINE_ANSWER["en"]

    out = respond(say("今日の天気は?", language="ja-JP"), [], None, live(), TABLES)
    assert out.answer == DECLINE_ANSWER["ja"]


# 제품 이름을 잘못 쓴 말 (2026-10-30: "인터버 종류 뭐있어?" 가 근거 없음으로 상담원에게 감)
MISSPELLED = "인터버 종류 뭐있어?"


def test_misspelled_product_is_answered_with_whole_catalog(analysis):
    analysis["classification"] = Classification(category=Category.TECH_SPEC, confidence=0.9)
    analysis["extraction"] = Extraction(language="ko")  # LLM 추출도 모델명이 없으면 비운다
    writer, judge = ScriptedWriter(), IntentJudge()

    out = respond(say(MISSPELLED), [], FakeDocs([tg(score=0.6)]), live(writer, judge), TABLES)

    assert out.handoff is False
    assert ("our_product", MISSPELLED) in judge.calls
    prompt = writer.prompts[0]
    assert "iS7 75kW VFD" in prompt and "Solar Inverter 25kW" in prompt  # 전체 제품 목록


def test_named_product_does_not_ask_jev_whether_it_is_ours(analysis):
    judge = IntentJudge()

    respond(say("인버터 종류 뭐있어?"), [], FakeDocs([tg(score=0.6)]), live(judge=judge), TABLES)

    assert not [c for c in judge.calls if isinstance(c, tuple) and c[0] == "our_product"]


@pytest.mark.parametrize("message", [MISSPELLED, OUT_OF_SCOPE])
def test_no_evidence_hands_off_when_jev_is_off(analysis, message):
    llm = LLMRouter(Settings(_env_file=None), writer=ScriptedWriter())  # Jev 꺼짐(fake)

    out = respond(say(message), [], FakeDocs([tg(score=0.6)]), llm, TABLES)

    assert out.handoff is True  # 우리 제품인지 판단이 안 되면 전처럼 넘긴다
    assert "couldn't find this" in out.handoff_reason


# 근거 없음 판단 점수 (2026-10-23 운영 사고: "UPS 보증기간…" 다음 "인버터 E.OC" 가 상담원으로 감)


class ScoredDocs(FakeDocs):
    """검색어에 따라 점수가 다른 검색기. hit(query) 가 None 이면 못 찾음."""

    def __init__(self, hit, calibrated=True):
        super().__init__([])
        self.hit = hit
        self.calibrated = calibrated

    def search(self, query, k=5, where=None):
        self.calls.append((query, k, where))
        score = self.hit(query)
        return [] if score is None else [tg(score=score)][:k]


def test_topic_change_in_the_conversation_does_not_hide_the_evidence(analysis):
    # 합친 최근 말(두 주제)은 점수가 낮아도 지금 말만으로 찾으면 근거가 있다
    docs = ScoredDocs(lambda q: 0.57 if "UPS" in q else 0.82)
    history = ["UPS 보증기간이랑 정격용량 알려줘", "보증 기간은 24개월입니다."]

    out = respond(say("인버터가 E.OC 에러로 멈췄어요."), history, docs, live(), TABLES)

    assert out.handoff is False
    assert [q for q, _, _ in docs.calls[:2]] == [
        "UPS 보증기간이랑 정격용량 알려줘\n인버터가 E.OC 에러로 멈췄어요.",
        "인버터가 E.OC 에러로 멈췄어요.",
    ]


def test_keyword_scores_are_not_compared_with_the_threshold(analysis):
    # 키워드 검색 점수 0.3 은 코사인 0.3 이 아니다 — 찾았으면 근거 있음
    out = respond(say(), [], ScoredDocs(lambda q: 0.3, calibrated=False), live(), TABLES)
    assert out.handoff is False

    # 못 찾았으면 근거 없음 → 우리 제품 이야기도 아니라서 제공하지 않는 정보라고 안내
    out = respond(
        say(OUT_OF_SCOPE), [], ScoredDocs(lambda q: None, calibrated=False), live(), TABLES
    )
    assert out.handoff is False and out.answer == DECLINE_ANSWER["ko"]


def test_keyword_search_also_looks_with_the_product_codes(analysis):
    # 키워드 검색은 한국어 낱말을 못 찾는다 → 대화의 제품 코드를 붙여 찾는다
    analysis["extraction"] = Extraction(language="ko")
    docs = ScoredDocs(lambda q: 0.4 if "INV-LSLV0075-S100" in q else None, calibrated=False)

    out = respond(say("인버터 과전류 트립"), [], docs, live(), TABLES)

    assert out.handoff is False
    assert any("INV-LSLV0075-S100" in q for q, _, _ in docs.calls)


def test_calibrated_search_does_not_get_product_codes_added(analysis):
    docs = ScoredDocs(lambda q: 0.8)
    respond(say("인버터 과전류 트립"), [], docs, live(), TABLES)

    assert not any("INV-" in q for q, _, _ in docs.calls)  # 기준값을 잰 검색어 그대로


@pytest.mark.parametrize(
    "message",
    [
        "인버터가 E.OC 에러로 멈췄어요.",
        "S100 보증기간이 얼마나 되나요?",
        "E.OC 떴어요",
        "무정전전원장치 배터리 교체 주기",
    ],
)
def test_our_product_is_answered_even_with_a_low_score(analysis, message):
    # 짧은 채팅 말은 맞는 문서를 찾아도 점수가 기준값 아래다 (pgvector 0.60~0.69)
    analysis["extraction"] = Extraction(language="ko")
    out = respond(say(message), [], FakeDocs([tg(score=0.62)]), live(), TABLES)

    assert out.handoff is False


def test_answer_prompt_has_product_data_without_prices(analysis):
    writer = ScriptedWriter()
    respond(say("S100 보증기간이랑 정격 용량"), [], FakeDocs([tg()]), live(writer), TABLES)

    prompt = writer.prompts[0]
    assert "[Product data · INV-LSLV0075-S100]" in prompt
    assert "- Warranty: 24 months" in prompt
    assert "Standard lead time" in prompt and "not a confirmed delivery date" in prompt
    assert "price" not in prompt.lower().split("reference documents:")[1]  # 견적은 결정 사항


def test_answer_prompt_has_the_policy_for_the_inquiry_type(analysis):
    analysis["classification"] = Classification(category=Category.RETURN, confidence=0.9)
    writer = ScriptedWriter()
    respond(say("MCCB 100AF 반품 정책 INFO"), [], FakeDocs([tg()]), live(writer), TABLES)

    assert "[POL-RETURN · 1]" in writer.prompts[0]


# 결정 유형: 정보만 묻는 말은 답하고, 결정이 필요하면 답할 수 있는 부분 + 문의서


def test_decision_type_asking_only_for_information_is_answered(analysis):
    # 실제 사례: "S100 보증기간이 얼마나 되나요?" → 보증 승인으로 보고 바로 넘어갔다
    analysis["classification"] = Classification(category=Category.WARRANTY, confidence=0.9)
    writer = ScriptedWriter("보증 기간은 24개월입니다.")
    out = respond(say("S100 보증기간 INFO"), [], FakeDocs([tg()]), live(writer), TABLES)

    assert out.handoff is False and out.form is None
    assert out.answer == "보증 기간은 24개월입니다."


def test_decision_with_other_questions_answers_them_and_opens_the_form(analysis):
    analysis["classification"] = Classification(category=Category.WARRANTY, confidence=0.9)
    writer = ScriptedWriter("정격 전류는 16 A입니다. 보증 수리는 문의서로 담당 팀이 처리합니다.")
    out = respond(
        say("S100 보증 수리 되나요? 정격 전류는요?"), [], FakeDocs([tg()]), live(writer), TABLES
    )

    assert out.handoff is True and out.form is not None and out.form.category == "WARRANTY"
    assert out.answer.startswith("정격 전류는 16 A")  # 답할 수 있는 부분을 버리지 않는다
    prompt = writer.prompts[0]
    assert "Warranty approval has to be decided" in prompt  # 결정 부분은 문의서로
    assert "E.OC: overcurrent" in prompt  # 나머지는 문서 근거로 답한다
    assert "Answer only the OTHER questions" in prompt


def test_partial_answer_failure_falls_back_to_the_handoff_notice(analysis):
    analysis["classification"] = Classification(category=Category.QUOTE, confidence=0.9)
    writer = ScriptedWriter(RuntimeError("down"), HANDOFF_KO)
    out = respond(say("PCS 20대 견적"), [], FakeDocs([tg()]), live(writer), TABLES)

    assert out.handoff is True and out.answer == HANDOFF_KO


def test_decision_judgement_is_only_asked_for_decision_categories(analysis):
    judge = IntentJudge()
    respond(say(), [], FakeDocs([tg()]), live(judge=judge), TABLES)  # DEFECT
    assert not [c for c in judge.calls if isinstance(c, tuple)]

    analysis["classification"] = Classification(category=Category.RETURN, confidence=0.9)
    respond(say("반품 정책 INFO"), [], FakeDocs([tg()]), live(judge=judge), TABLES)
    assert ("decision", "반품 정책 INFO") in judge.calls


def test_decision_judgement_failure_hands_off_as_before(analysis):
    class Broken(IntentJudge):
        def judge(self, prompt, options):
            if "Customer's message:" in prompt:
                raise RuntimeError("jev down")
            return super().judge(prompt, options)

    analysis["classification"] = Classification(category=Category.WARRANTY, confidence=0.9)
    out = respond(say("보증 INFO"), [], FakeDocs([tg()]), live(judge=Broken()), TABLES)

    assert out.handoff is True


# 아직 질문 전인 말 (Jev GENERAL) · 제품군 이름


def test_general_opener_asks_back_instead_of_handing_off(analysis):
    # 실제 사례: "무정전전원장치에 대해 궁금한 점이 있어요" → 바로 상담원으로 넘어갔다
    analysis["extraction"] = Extraction(language="ko")
    writer = ScriptedWriter("어떤 점이 궁금하신가요?")
    out = respond(
        say("무정전전원장치에 대해 궁금한 점이 있어요"),
        [],
        FakeDocs([tg(score=0.55)]),
        live(writer),
        TABLES,
    )

    assert out.handoff is False
    assert out.answer == "어떤 점이 궁금하신가요?"
    assert "UPS products: Online UPS 10kVA" in writer.prompts[0]  # 제품군 제품이 답변 맥락
    assert out.navigation.rule_id is not None and out.navigation.product_code is None
    assert out.navigation.candidates == ["UPS-LSU-10K"]  # 화면에 "제품 선택" 버튼


@pytest.mark.parametrize("docs", [None, FakeDocs([])])
def test_general_opener_without_any_documents_still_asks_back(analysis, docs):
    out = respond(say("PLC 궁금한 게 있어요"), [], docs, live(), TABLES)

    assert out.handoff is False


def test_general_does_not_cancel_other_handoff_reasons(analysis):
    analysis["classification"] = Classification(category=Category.QUOTE, confidence=0.9)
    out = respond(say("견적 궁금"), [], FakeDocs([tg()]), live(), TABLES)
    assert out.handoff is True and "quotation" in out.handoff_reason

    out = respond(say("궁금", unresolved=True), [], FakeDocs([tg()]), live(), TABLES)
    assert out.handoff is True


def test_family_name_fills_the_family_for_navigation(analysis):
    analysis["extraction"] = Extraction(language="ko")
    out = respond(say("태양광 인버터 설치 간격은?"), [], FakeDocs([tg()]), live(), TABLES)

    assert out.navigation.candidates == ["PV-INV-SOLAR-25"]


def test_family_from_an_earlier_message_is_kept(analysis):
    analysis["extraction"] = Extraction(language="ko")
    history = ["UPS 문의드려요", "어떤 점이 궁금하신가요?"]
    out = respond(say("배터리 교체 주기는요?"), history, FakeDocs([tg()]), live(), TABLES)

    assert out.navigation.candidates == ["UPS-LSU-10K"]


@pytest.mark.parametrize(
    ("text", "family"),
    [
        ("무정전전원장치에 대해 궁금한 점이 있어요", "UPS"),
        ("태양광 제품 문의드려요", "PV"),
        ("태양광 인버터 문의", "PV"),  # 긴 낱말이 이긴다 (인버터 → DRIVE 아님)
        ("인버터 에러", "DRIVE"),
        ("고압 차단기 정격", "MV_EQUIP"),  # 띄어 써도 찾는다
        ("누전차단기 문의", "LV_BREAKER"),
        ("I need help with a solar inverter", "PV"),
        ("vacuum circuit breaker spec", "MV_EQUIP"),
        ("変圧器について", "TRANSFORMER"),
        ("太陽光インバーターについて質問があります", "PV"),  # インバータ(DRIVE)보다 길다
        ("光伏逆变器故障", "PV"),
        ("不间断电源问题", "UPS"),
        ("Need 20 pcs quote", None),  # 수량 pcs 는 ESS PCS 가 아니다
        ("setup groups", None),  # 낱말 안의 ups 는 아니다
        ("오늘 날씨 어때", None),
    ],
)
def test_mentioned_family(text, family):
    assert agent.mentioned_family([text]) == family


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
    writer = ScriptedWriter(HANDOFF_KO, "Subject\n\nBody")  # 번역, 문의서 요약 순서

    out = respond(say(unresolved=True), [], FakeDocs([tg()]), live(writer), TABLES)

    assert out.answer == HANDOFF_KO
    assert "Translate the text into Korean" in writer.prompts[0]


@pytest.mark.parametrize(
    "outputs",
    [
        [RuntimeError("boom")] * 3,  # 번역 호출 실패
        ["Since this wasn't resolved, we'll pass it to a support engineer."] * 3,  # 영어 그대로
        [RuntimeError("boom"), "영어", "still English text, not Korean at all"],
    ],
)
def test_handoff_answer_is_never_sent_in_english_to_other_languages(analysis, outputs):
    """세 번 옮겨도 고객 언어로 확인되지 않으면 영어가 아니라 언어별 고정 문장."""
    writer = ScriptedWriter(*outputs, "Subject\n\nBody")

    out = respond(say(unresolved=True), [], FakeDocs([tg()]), live(writer), TABLES)

    assert out.answer == agent.HANDOFF_FALLBACK["ko"]
    assert sum(p.startswith("Translate the text") for p in writer.prompts) == 3
    assert out.form is not None and out.form.subject == "Subject"


def test_handoff_retry_after_a_wrong_language_answer(analysis):
    writer = ScriptedWriter("still English text, not Korean at all", HANDOFF_KO, "S\n\nB")

    out = respond(say(unresolved=True), [], FakeDocs([tg()]), live(writer), TABLES)

    assert out.answer == HANDOFF_KO


def test_handoff_without_llm_uses_the_fixed_sentence_in_customer_language(analysis):
    out = respond(
        say(unresolved=True), [], FakeDocs([tg()]), LLMRouter(Settings(_env_file=None)), TABLES
    )

    assert out.answer == agent.HANDOFF_FALLBACK["ko"]


def test_unknown_language_falls_back_to_english(analysis):
    out = respond(
        say(unresolved=True, language="xx"),
        [],
        FakeDocs([tg()]),
        LLMRouter(Settings(_env_file=None)),
        TABLES,
    )

    assert out.answer == agent.HANDOFF_FALLBACK["en"]


def test_fallback_sentences_cover_customer_languages() -> None:
    from cs_agent.agents.drafting import _CUSTOMER_LANGUAGES
    from cs_agent.agents.info_request import in_language

    assert set(agent.HANDOFF_FALLBACK) == set(_CUSTOMER_LANGUAGES)
    for code, text in agent.HANDOFF_FALLBACK.items():
        assert in_language(text, code), code  # 고정 문장도 그 언어로 확인된다


@pytest.mark.parametrize(
    ("history", "message", "language"),
    [
        ([], "S100 인버터가 가속할 때 E.OC 에러가 떠요", "ko"),
        ([], "Mi variador S100 se dispara con E.OC al acelerar", "es"),
        (["S100 가속 중 E.OC 가 떠요", ADVICE], "E.OC?", "ko"),  # 짧은 말은 지난 고객 말로
        ([], "S100 E.OC", "en"),  # 글자가 거의 없으면 영어
        ([], "S100 加速时出现 E.OC 故障", "zh"),
        ([], "S100 で加速中に E.OC が出ます", "ja"),  # 한자가 섞여도 가나가 있으면 일본어
    ],
)
def test_language_is_detected_when_the_screen_does_not_send_it(
    analysis, history, message, language
):
    writer = ScriptedWriter()

    respond(ChatIn(session_id="s", message=message), history, FakeDocs([tg()]), live(writer))

    assert f"in {agent.language_name(language)}" in writer.prompts[0]


def test_english_customers_get_the_english_text_without_a_model_call(analysis):
    writer = ScriptedWriter("Subject\n\nBody")

    out = respond(say(unresolved=True, language="en"), [], FakeDocs([tg()]), live(writer), TABLES)

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


# 응답 시간: LLM 추출은 답변 작성과 함께 돈다


def test_llm_extraction_runs_while_the_answer_is_written(analysis, monkeypatch):
    import time

    extracted = analysis["extraction"]

    def slow_extract(inquiry, tables, **kw):
        time.sleep(0.4)
        return extracted

    class SlowWriter(ScriptedWriter):
        def write(self, prompt):
            time.sleep(0.4)
            return super().write(prompt)

    monkeypatch.setattr(agent, "extract", slow_extract)
    started = time.monotonic()

    out = respond(say(), [], FakeDocs([tg()]), live(SlowWriter()), TABLES)

    assert time.monotonic() - started < 0.75  # 0.4 + 0.4 를 더한 시간이 아니다
    assert out.navigation.tab == "faults"


def test_rule_extraction_feeds_the_answer_and_llm_extraction_the_screen(analysis):
    """답변은 규칙 추출(메시지에 S100)로, 화면 이동·ask_fields 는 LLM 추출로."""
    analysis["extraction"] = Extraction(
        product_code=S100, product_family="DRIVE", error_code="E.OC", serial_no="SN-1"
    )
    writer = ScriptedWriter()

    out = respond(say("S100 가속 중 트립"), [], FakeDocs([tg()]), live(writer), TABLES)

    assert "LSLV S100 7.5kW VFD" in writer.prompts[0]
    assert out.navigation.anchor == "E.OC"  # 메시지에는 없고 LLM 추출에만 있다
    assert "serial_no" not in out.ask_fields


def test_failed_llm_extraction_falls_back_to_rule_extraction(analysis, monkeypatch):
    def broken(inquiry, tables, **kw):
        raise AnalysisError("structured_extraction_failed")

    monkeypatch.setattr(agent, "extract", broken)

    out = respond(say("S100 가속 중 E.OC"), [], FakeDocs([tg()]), live(), TABLES)

    assert out.handoff is False
    assert (out.navigation.product_code, out.navigation.anchor) == (S100, "E.OC")


def test_failed_llm_extraction_still_fills_the_form_on_handoff(analysis, monkeypatch):
    monkeypatch.setattr(
        agent, "extract", lambda *a, **k: (_ for _ in ()).throw(TimeoutError("slow"))
    )

    out = respond(
        say("S100 E.OC 해결 안 됐어요", unresolved=True), [], FakeDocs([tg()]), live(), TABLES
    )

    assert out.form is not None
    assert out.form.fields["error_code"] == "E.OC"  # 규칙 추출 값


def test_slow_llm_extraction_does_not_hold_the_answer(analysis, monkeypatch):
    """전환이 아니면 답변 뒤 EXTRACT_GRACE_S 만 기다리고 규칙 추출로 답한다."""
    import threading
    import time

    release = threading.Event()

    def stuck(inquiry, tables, **kw):
        release.wait(5)
        return analysis["extraction"]

    monkeypatch.setattr(agent, "extract", stuck)
    monkeypatch.setattr(agent, "EXTRACT_GRACE_S", 0.1)
    started = time.monotonic()

    out = respond(say("S100 가속 중 E.OC"), [], FakeDocs([tg()]), live(), TABLES)
    release.set()

    assert time.monotonic() - started < 1.0
    assert (out.navigation.product_code, out.navigation.anchor) == (S100, "E.OC")  # 규칙 추출
