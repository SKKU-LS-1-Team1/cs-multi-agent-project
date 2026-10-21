# 문의서 작성 에이전트 (CSA-34 · 담당 조수빈 · Sprint 2)
#
# 챗봇이 문의하기로 넘길 때, 대화에서 얻은 값으로 문의서 칸을 미리 채운다 (기획서 5.5 표).
# 제출은 고객이 확인한 뒤 직접 누른다. 고객이 고친 값이 우선하고, 고친 칸은 추출 정확도 측정에 쓴다.
#
# 할 일
# 1. 유형별 필수 항목 목록: rules/engine.py 의 required_info(family, category) 로 칸을 만든다.
# 2. 대화에서 찾은 값(제품, 에러코드, 시리얼, 펌웨어, 수량 …)을 fields 에 넣고,
#    빈 필수 항목은 missing_required 에 넣는다 (화면에서 빨간 칸, 채우기 전 제출 불가).
# 3. subject·body: Gemini로 대화를 요약한다. 이미 안내받은 조치와 그 결과를 꼭 넣는다
#    ("가속 시간 조정 후에도 재발") — 상담원이 같은 조치를 다시 안내하지 않게.
# 4. 국가·언어·회사·연락처는 로그인 고객 정보에서 (화면 쪽에서 합친다).
#
# 완료 기준: 기획서 5.5 예시(불량 문의)대로 채워진 문의서가 나온다
#
# 구현 메모
# - fields 에는 값이 있는 필수 항목만, missing_required 에는 값이 없는 필수 항목을 넣는다. 화면
#   (InquiryForm.tsx)이 둘을 합쳐 칸을 만들므로 같은 항목이 양쪽에 있으면 안 된다.
# - 값은 extraction.field_values 가 먼저고, 없으면 error_code · serial_no · fw_version(current_fw) ·
#   제품명(product_model)으로 채운다. 기준표 항목(info_field_codebook)이 아니거나 빈 값은 버린다.
# - transcript 는 챗봇 기록 순서(api/chat.py): 고객 말, 챗봇 답변, 고객 말 … 로 번갈아 쌓인다.
#   짝수 번째가 고객, 홀수 번째가 챗봇이라고 보고, 챗봇 쪽에서 "이미 안내받은 조치"를 뽑는다.
# - llm 은 선택이다. 없거나 꺼져 있거나 실패하거나 제목·본문 모양이 아니면 대화에서 규칙으로 만든다.
#   요약이 실패해도 칸 채우기는 영향을 받지 않는다.
# - 국가·언어·회사·연락처는 로그인 고객 정보라 화면 쪽에서 합친다. 첨부(대화 전문·본 문서 목록)는
#   InquiryDraftForm 에 필드가 없어 여기서 다루지 않는다.
import logging

from pydantic import BaseModel, Field

from cs_agent.llm.router import LLMRouter
from cs_agent.rules.engine import required_info
from cs_agent.rules.tables import RefTables, load_tables
from cs_agent.schemas import Classification, Extraction

_LOGGER = logging.getLogger(__name__)

SUBJECT_MAX_CHARS = 100

SUMMARY_PROMPT = """You prepare the inquiry form a customer will review and submit to support.
Summarize the chat below into a subject and a message body.

Rules:
- Write in the customer's language ({language}).
- Output the subject on the first line, a blank line, then the body. No labels, no markdown.
- The subject is one short line. The body states the problem and the facts the customer gave.
- The body MUST say which steps the assistant already advised and what happened after them,
  so the support engineer does not repeat them.
- Use only facts from the chat and the known fields. Do not invent values or promise anything.

Inquiry type: {category}
Product: {product}
Known fields: {fields}

Customer messages:
{customer}

Assistant advice already given:
{advice}
"""


class InquiryDraftForm(BaseModel):
    """문의하기 화면에 넘기는 문의서 초안. 화면(frontend/src/api/client.ts)과 같은 모양."""

    category: str | None = None
    product_code: str | None = None
    fields: dict[str, str] = Field(default_factory=dict)
    missing_required: list[str] = Field(default_factory=list)
    subject: str = ""
    body: str = ""


def fill_form(
    classification: Classification,
    extraction: Extraction,
    transcript: list[str],
    llm: LLMRouter | None = None,
    tables: RefTables | None = None,
) -> InquiryDraftForm:
    """대화에서 얻은 값으로 문의서를 미리 채운다. 위 '할 일' 참고."""
    tables = tables or load_tables()
    product = tables.products.get(extraction.product_code or "")
    family = extraction.product_family or (product.family if product else None)
    required, _ = required_info(family, classification.category, tables)

    known = _known_values(extraction, product.name if product else None, tables)
    fields = {name: known[name] for name in required if name in known}
    subject, body = _summary(
        classification, extraction, product.name if product else None, fields, transcript, llm
    )
    return InquiryDraftForm(
        category=str(classification.category),
        product_code=product.code if product else None,
        fields=fields,
        missing_required=[name for name in required if name not in fields],
        subject=subject,
        body=body,
    )


def _known_values(extraction: Extraction, product_name: str | None, tables: RefTables) -> dict:
    values = {
        "error_code": extraction.error_code,
        "serial_no": extraction.serial_no,
        "current_fw": extraction.fw_version,
        "product_model": product_name,
    }
    values.update(extraction.field_values)  # 확인된 값이 먼저다
    return {
        name: value.strip()
        for name, value in values.items()
        if name in tables.field_labels and value and value.strip()
    }


def _summary(
    classification: Classification,
    extraction: Extraction,
    product_name: str | None,
    fields: dict[str, str],
    transcript: list[str],
    llm: LLMRouter | None,
) -> tuple[str, str]:
    customer, advice = transcript[0::2], transcript[1::2]
    if not customer:
        return "", ""
    if llm is not None and llm.enabled:
        prompt = SUMMARY_PROMPT.format(
            language=extraction.language or "same language as the customer messages",
            category=classification.category,
            product=product_name or "unknown",
            fields=fields or "none",
            customer=_bullets(customer),
            advice=_bullets(advice) if advice else "- (none)",
        )
        try:
            parsed = _parse_summary(llm.write("inquiry_summary", prompt))
        except Exception as e:  # 요약이 실패해도 칸 채우기는 돌려준다
            _LOGGER.warning("문의서 요약 실패 → 대화에서 규칙으로 만든다: %s", e)
            parsed = None
        if parsed:
            return parsed
    return _fallback_summary(customer, advice)


def _bullets(messages: list[str]) -> str:
    return "\n".join(f"- {m.strip()}" for m in messages)


def _parse_summary(text: str) -> tuple[str, str] | None:
    """첫 줄 = 제목, 나머지 = 본문. 둘 중 하나가 비면 쓸 수 없다."""
    subject, _, body = text.strip().partition("\n")
    subject, body = subject.strip()[:SUBJECT_MAX_CHARS], body.strip()
    return (subject, body) if subject and body else None


def _fallback_summary(customer: list[str], advice: list[str]) -> tuple[str, str]:
    subject = " ".join(customer[0].split())[:SUBJECT_MAX_CHARS]
    body = "Customer messages:\n" + _bullets(customer)
    if advice:
        body += "\n\nAlready advised in chat:\n" + _bullets(advice)
    return subject, body
