"""챗봇 대화 에이전트 (CSA-32 · 담당 조수빈).

고객 질문에 공개 문서를 근거로 답하고, 유형별로 빠진 필수 항목을 미리 묻는다.
응답에는 답변 문장과 함께 화면 이동 지시(CSA-33)와, 전환할 때는 채운 문의서(CSA-34)가 담긴다.
견적 확정·보증 승인·원인 단정은 하지 않고 문의하기로 넘긴다.
"""

from pydantic import BaseModel, Field

from cs_agent.agents import analysis
from cs_agent.agents.retrieval import Retriever
from cs_agent.chatbot.form_filler import InquiryDraftForm, fill_form
from cs_agent.chatbot.handoff import should_handoff
from cs_agent.chatbot.navigation import Navigation, decide
from cs_agent.llm.router import LLMRouter
from cs_agent.rules.engine import required_info
from cs_agent.schemas import Evidence, InquiryIn


class ChatIn(BaseModel):
    session_id: str
    message: str
    language: str = "en"
    viewing_product: str | None = None  # 대시보드에서 보고 있는 제품 (양방향 연동)
    unresolved: bool = False


class ChatOut(BaseModel):
    answer: str
    navigation: Navigation
    evidence: list[Evidence] = Field(default_factory=list)
    ask_fields: list[str] = Field(default_factory=list)
    handoff: bool = False
    handoff_reason: str = ""
    form: InquiryDraftForm | None = None


def respond(chat: ChatIn, history: list[str], docs: Retriever, llm: LLMRouter) -> ChatOut:
    transcript = [*history, chat.message]
    inquiry = InquiryIn(
        channel="CHAT",
        language=chat.language,
        body="\n".join(transcript),
        product_code=chat.viewing_product,
    )
    classification = analysis.classify(inquiry, llm)
    extraction = analysis.extract(inquiry)
    where = {"product_code": extraction.product_code} if extraction.product_code else None
    hits = docs.search(chat.message, k=3, where=where)
    nav = decide(extraction, classification)

    decision = should_handoff(
        classification.category, hits[0].score if hits else 0.0, customer_unresolved=chat.unresolved
    )
    if decision.handoff:
        return ChatOut(
            answer=decision.reason + " 문의하기 화면으로 이동합니다.",
            navigation=nav,
            evidence=hits,
            handoff=True,
            handoff_reason=decision.reason,
            form=fill_form(classification, extraction, transcript),
        )

    required, _ = required_info(extraction.product_family, classification.category)
    ask = [f for f in required if f not in extraction.provided_info][:2]
    if llm.enabled:
        sources = "\n".join(f"[{e.doc_id} {e.section}] {e.text}" for e in hits)
        answer = llm.write(
            "chat_answer",
            f"고객 언어({chat.language})로, 근거 안에서만 답하라.\n"
            f"근거:\n{sources}\n\n질문: {chat.message}",
        )
    else:
        answer = hits[0].text[:300] if hits else "관련 문서를 찾고 있습니다."
    return ChatOut(answer=answer, navigation=nav, evidence=hits, ask_fields=ask)
