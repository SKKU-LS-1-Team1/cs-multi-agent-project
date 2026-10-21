# 챗봇 대화 에이전트 (CSA-32 · 담당 조수빈 · Sprint 2)
#
# api/chat.py 의 POST /api/chat 이 부른다. 대화 기록은 cache/store.py 의 ChatSessionStore(Redis)에
#   있다.
#
# 할 일
# 1. respond(): 대화 기록 + 새 메시지로 InquiryIn 을 만들고 (viewing_product 를 product_code 로),
#    문의 분석(agents/analysis.py)으로 유형·제품·에러코드를 뽑는다. 새로 만들지 말고 재사용한다.
# 2. 지식 검색(agents/retrieval.py)으로 근거를 찾는다. 제품을 알면 where={"product_code": …}.
# 3. 화면 이동(chatbot/navigation.py decide)을 정한다.
# 4. 문의 전환(chatbot/handoff.py should_handoff)이면: 이유 한 줄 + "문의하기로 이동" 답변,
#    handoff=True, form=fill_form(...) (chatbot/form_filler.py).
# 5. 아니면 Gemini로 고객 언어 답변: llm.write("chat_answer", …). 공개 문서 근거 안에서만 답한다.
#    견적 금액 확정·보증 승인·원인 단정은 하지 않는다.
# 6. 유형별 필수 항목 중 아직 안 나온 것 1~2개를 ask_fields 에 넣어 미리 묻는다 (예: 불량 → 시리얼).
#    필수 항목 목록은 rules/engine.py required_info().
# 7. 대화 의도·재문의·해결 여부 판단은 Jev(llm.judge)로 (기획서 9.2).
#
# 완료 기준: 기획서 5.4·5.5 시나리오(S100 E.OC → 고장 탭 → 재발 → 문의하기 자동 채움)가 끝까지 동작
#
# 참고: 기획서 v10 5장
#
# 구현 메모
# - history 는 ChatSessionStore 의 기록(고객, 챗봇, 고객 … 순서)이다. 분석(analysis.py)은 역할이
#   붙은 대화를 받으므로 짝수 번째를 user, 홀수 번째를 assistant 로 바꿔서 넘긴다. 기록이 홀수 개면
#   (오래된 쪽이 잘려 나간 경우) 맨 앞 하나를 버려 순서를 맞춘다.
# - 문의 전환의 best_score 는 제품 필터 없이 찾은 docs 1등 점수여야 한다(handoff.py 기준값을 그렇게
#   쟀다). 그래서 답변 근거와 따로 한 번 더 찾는다. 검색기가 없으면 근거 없음(0.0)으로 본다.
#   로컬 키워드 검색(KeywordRetriever)의 점수는 척도가 달라 기준값(0.70)과 비교할 수 없다. pgvector
#   검색일 때만 믿을 수 있다.
# - 재발 횟수(remote_attempts)와 "해결 안 됐다 · 상담원 연결" 요청은 Jev 판단(llm.judge)으로 센다.
#   진단형(불량·설치·펌웨어)일 때만 지난 고객 말을 다시 판단하고, 판단은 라우터 캐시에 남는다.
#   Jev 가 꺼져 있으면(fake) 판단하지 않은 것으로 본다.
# - 분석이 실패하면(AnalysisError) 분류 없이 계속한다: 화면은 옮기지 않고, 대시보드에서 보던
#   제품으로 검색·답변한다. 분류가 없으면 문의서 초안(form)도 만들 수 없다.
# - 고객 언어는 추출된 언어가 먼저고, 없으면 ChatIn.language 다.
# - 안전 신호(연기·화재·감전)는 여기서 따로 막지 않는다. 필요하면 handoff 조건에 더한다.
import logging

from pydantic import BaseModel, Field

from cs_agent.agents.analysis import AnalysisError, classify, extract
from cs_agent.agents.retrieval import Retriever, finalize_evidence, first_pass
from cs_agent.chatbot.form_filler import InquiryDraftForm, fill_form
from cs_agent.chatbot.handoff import should_handoff
from cs_agent.chatbot.navigation import Navigation, decide
from cs_agent.domain import BUNDLE_OF, Bundle
from cs_agent.llm.router import LLMRouter
from cs_agent.rules.engine import UNKNOWN_PRODUCT_FIELD, required_info
from cs_agent.rules.tables import RefTables, load_tables
from cs_agent.schemas import Classification, Evidence, Extraction, InquiryIn

_LOGGER = logging.getLogger(__name__)

CHANNEL = "CHAT"
ASK_FIELDS_MAX = 2  # 한 번에 미리 묻는 필수 항목 수
QUERY_MESSAGES = 3  # 검색어로 쓰는 최근 고객 말 수
INTENT_HISTORY = 4  # 재발을 다시 판단하는 지난 고객 말 수
EVIDENCE_CHARS = 1500  # 근거 한 개당 프롬프트에 넣는 글자 수

RECURRENCE, REQUEST_AGENT, OTHER = "RECURRENCE", "REQUEST_AGENT", "OTHER"
INTENT_OPTIONS = [RECURRENCE, REQUEST_AGENT, OTHER]

INTENT_PROMPT = """Classify the customer's latest message in a support chat.

RECURRENCE: the customer says the problem happened again or still continues after trying the
assistant's earlier advice.
REQUEST_AGENT: the customer says the problem is not solved, or asks to talk to a person or to
submit an inquiry.
OTHER: anything else, including a new question.

Assistant's previous advice:
{advice}

Customer's latest message:
{message}
"""

CHAT_PROMPT = """You are the customer-support chatbot of an industrial electrical equipment maker.
Answer the customer's latest message in {language}.

Rules:
- Use ONLY the reference documents below. If they do not contain the answer, say you could not
  find it and that a support engineer can help.
- Never confirm a quotation amount, approve a warranty or a return, or state a definite root cause.
  Offer to open the inquiry form instead.
- Be concise: a few sentences. When you give a value or a step, name the document section it
  comes from.
- Do not repeat steps the assistant already advised earlier in the conversation. Build on them.

Product: {product}
Inquiry type: {category}

Reference documents:
{evidence}

Conversation so far:
{conversation}

Customer's latest message:
{message}
"""

TRANSLATE_PROMPT = """Translate the text into {language}. Output only the translation.

{text}
"""

HANDOFF_SUFFIX = " I'll open the inquiry form with what we've discussed so far."


class ChatIn(BaseModel):
    session_id: str
    message: str
    language: str = "en"
    viewing_product: str | None = None  # 대시보드에서 보고 있는 제품 (양방향 연동)
    unresolved: bool = False  # 고객이 "해결 안 됐어요"를 누름


class ChatOut(BaseModel):
    answer: str
    navigation: Navigation
    evidence: list[Evidence] = Field(default_factory=list)
    ask_fields: list[str] = Field(default_factory=list)
    handoff: bool = False
    handoff_reason: str = ""
    form: InquiryDraftForm | None = None


def respond(
    chat: ChatIn,
    history: list[str],
    docs: Retriever | None,
    llm: LLMRouter,
    tables: RefTables | None = None,
) -> ChatOut:
    """대화 기록 + 새 메시지 → 챗봇 응답. 위 '할 일' 참고."""
    tables = tables or load_tables()
    history = history[len(history) % 2 :]  # 고객으로 시작하도록 맞춘다
    customer, advice = history[0::2], history[1::2]
    transcript = [
        {"role": "user" if i % 2 == 0 else "assistant", "content": m} for i, m in enumerate(history)
    ]
    viewing = chat.viewing_product if chat.viewing_product in tables.products else None
    inquiry = InquiryIn(
        channel=CHANNEL, language=chat.language, body=chat.message, product_code=viewing
    )

    classification, extraction = _analyze(inquiry, transcript, viewing, llm, tables)
    category = classification.category if classification else None
    language = extraction.language or chat.language

    query = "\n".join([*customer[-(QUERY_MESSAGES - 1) :], chat.message])
    best_score = _best_score(docs, query)
    unresolved, attempts = _intent_signals(chat, customer, advice, category, llm)
    decision = should_handoff(category, best_score, unresolved or chat.unresolved, attempts)

    navigation = decide(extraction, classification, tables) if classification else Navigation()
    candidates = first_pass(docs, None, query) if docs is not None else []
    evidence = finalize_evidence(candidates, extraction, category=category)

    if decision.handoff:
        form = (
            fill_form(classification, extraction, [*history, chat.message], llm, tables)
            if classification
            else None
        )
        return ChatOut(
            answer=_handoff_answer(decision.reason, language, llm),
            navigation=navigation,
            evidence=evidence,
            handoff=True,
            handoff_reason=decision.reason,
            form=form,
        )

    product = tables.products.get(extraction.product_code or "")
    prompt = CHAT_PROMPT.format(
        language=language,
        product=product.name if product else "unknown",
        category=category or "unknown",
        evidence=_evidence_block(evidence),
        conversation=_conversation(history) or "(first message)",
        message=chat.message,
    )
    return ChatOut(
        answer=llm.write("chat_answer", prompt),
        navigation=navigation,
        evidence=evidence,
        ask_fields=_ask_fields(extraction, category, product is not None, tables),
    )


def _analyze(
    inquiry: InquiryIn,
    transcript: list[dict[str, str]],
    viewing: str | None,
    llm: LLMRouter,
    tables: RefTables,
) -> tuple[Classification | None, Extraction]:
    """분류·추출. 실패하면 분류 없이, 보던 제품만 아는 추출로 계속한다."""
    try:
        classification = classify(inquiry, llm, transcript=transcript, include_secondary=False)
        extraction = extract(
            inquiry,
            tables,
            llm=llm,
            transcript=transcript,
            category=classification.category,
        )
    except AnalysisError as e:
        _LOGGER.warning("챗봇 분석 실패 → 분류 없이 계속한다: %s", e)
        classification, extraction = None, Extraction()
    if extraction.product_code is None and viewing:  # 보고 있는 화면이 대화의 맥락이다
        extraction = extraction.model_copy(
            update={
                "product_code": viewing,
                "product_family": extraction.product_family or tables.products[viewing].family,
            }
        )
    return classification, extraction


def _best_score(docs: Retriever | None, query: str) -> float:
    """제품 필터 없이 찾은 docs 1등 점수. 검색기가 없거나 못 찾으면 0.0 (근거 없음)."""
    if docs is None:
        return 0.0
    top = docs.search(query, 1)
    return top[0].score if top else 0.0


def _intent_signals(
    chat: ChatIn, customer: list[str], advice: list[str], category, llm: LLMRouter
) -> tuple[bool, int]:
    """(상담원 연결 요청 여부, 원격 조치 재발 횟수). 위 구현 메모 참고."""
    last_advice = advice[-1] if advice else None
    current = _intent(llm, last_advice, chat.message)
    attempts = 1 if current == RECURRENCE and last_advice else 0
    if category is not None and BUNDLE_OF.get(category) == Bundle.DIAGNOSIS:
        # 첫 고객 말은 조치를 받기 전이라 재발일 수 없다
        for i in range(max(1, len(customer) - INTENT_HISTORY), len(customer)):
            if i - 1 < len(advice) and _intent(llm, advice[i - 1], customer[i]) == RECURRENCE:
                attempts += 1
    return current == REQUEST_AGENT, attempts


def _intent(llm: LLMRouter, advice: str | None, message: str) -> str:
    prompt = INTENT_PROMPT.format(advice=advice or "(none)", message=message)
    try:
        judgement = llm.judge("chat_intent", prompt, INTENT_OPTIONS)
    except Exception as e:  # 판단이 안 되면 아무 일도 없었던 것으로 본다
        _LOGGER.warning("챗봇 대화 의도 판단 실패: %s", e)
        return OTHER
    return OTHER if judgement.model == "fake" else judgement.answer


def _handoff_answer(reason: str, language: str, llm: LLMRouter) -> str:
    text = reason + HANDOFF_SUFFIX
    if language.lower().startswith("en") or not llm.enabled:
        return text
    try:
        return llm.write("chat_handoff", TRANSLATE_PROMPT.format(language=language, text=text))
    except Exception as e:  # 옮기지 못하면 영어 그대로
        _LOGGER.warning("전환 안내 번역 실패: %s", e)
        return text


def _ask_fields(
    extraction: Extraction, category, product_known: bool, tables: RefTables
) -> list[str]:
    """아직 안 나온 필수 항목 중 처리를 막는 것부터 1~2개."""
    if category is None:
        return []
    required, blocking = required_info(extraction.product_family, category, tables)
    have = set(extraction.provided_info) | set(extraction.field_values)
    for name, value in (
        (UNKNOWN_PRODUCT_FIELD, product_known),
        ("error_code", extraction.error_code),
        ("serial_no", extraction.serial_no),
        ("current_fw", extraction.fw_version),
    ):
        if value:
            have.add(name)
    missing = [f for f in required if f not in have]
    missing.sort(key=lambda f: f not in blocking)  # 정렬은 안정적이라 나머지 순서는 그대로
    return missing[:ASK_FIELDS_MAX]


def _evidence_block(evidence: list[Evidence]) -> str:
    if not evidence:
        return "(none)"
    return "\n\n".join(
        f"[{e.doc_id}{' · ' + e.section if e.section else ''}]\n{e.text[:EVIDENCE_CHARS]}"
        for e in evidence
    )


def _conversation(history: list[str]) -> str:
    return "\n".join(
        f"{'Customer' if i % 2 == 0 else 'Assistant'}: {m.strip()}" for i, m in enumerate(history)
    )
