"""② 분류 · ③ 추출: 문의 분석 에이전트 (CSA-26 · 담당 김도연).

유형(10개)·제품(23개)·긴급 여부는 Jev로 판단하고, 에러코드·시리얼·펌웨어처럼 형식이 정해진
값은 코드로 먼저 찾는다 (기획서 9.2). LLM이 꺼져 있으면 키워드 규칙으로 동작한다.
챗봇(CSA-32)과 문의서 자동 채움(CSA-34)도 이 모듈을 그대로 쓴다.
"""

import re

from cs_agent.domain import Category, Urgency
from cs_agent.llm.router import LLMRouter
from cs_agent.rules.tables import RefTables, load_tables
from cs_agent.schemas import Classification, Extraction, InquiryIn

# TODO(CSA-26): train 분할로 학습한 분류기(TF-IDF, valid 99.0%)로 교체하고 확률을 쓴다.
_CATEGORY_KEYWORDS: list[tuple[Category, tuple[str, ...]]] = [
    (Category.RETURN, ("return", "rma", "refund", "반품")),
    (Category.WARRANTY, ("warranty", "guarantee", "보증")),
    (Category.QUOTE, ("quote", "quotation", "price", "견적", "가격")),
    (Category.ORDER_LEAD, ("lead time", "delivery", "po ", "order status", "납기")),
    (Category.FW_UPDATE, ("firmware", "fw ", "펌웨어")),
    (Category.DEFECT, ("error", "fault", "trip", "alarm", "고장", "에러", "불량")),
    (Category.INSTALL, ("install", "wiring", "commissioning", "설치", "배선")),
    (Category.COMPLIANCE, ("certificate", "ce ", "ul ", "iec", "kc ", "인증", "규격")),
    (Category.MANUAL, ("manual", "document", "guide", "매뉴얼", "설명서")),
]

_URGENCY_KEYWORDS: list[tuple[Urgency, tuple[str, ...]]] = [
    (Urgency.SAFETY, ("smoke", "fire", "burn", "shock", "spark", "연기", "화재", "감전")),
    (Urgency.SITE_DOWN, ("site down", "line stopped", "plant down", "stopped", "가동 중단")),
    (Urgency.PROD_IMPACT, ("production", "생산")),
    (Urgency.COMMISSION, ("commissioning", "시운전")),
    (Urgency.DEADLINE, ("deadline", "urgent", "asap", "by tomorrow", "급함")),
]

ERROR_CODE_RE = re.compile(r"\b(?:E|ERR|F|A)(?:[.\-][A-Z0-9]{1,4}|\d{1,3})\b")
SERIAL_RE = re.compile(r"\bS/?N[:\s#=]*([A-Z0-9\-]{6,})\b", re.IGNORECASE)
FW_RE = re.compile(r"\b(?:fw|firmware|ver(?:sion)?)\s*[:=]?\s*v?(\d+\.\d+(?:\.\d+)?)", re.I)


def _has_any(text: str, words: tuple[str, ...]) -> bool:
    """영문은 단어 경계로, 한글은 부분 문자열로 찾는다 ("rma"가 "confirmation"에 걸리지 않게)."""
    suffix = r"(?:s|es|ed|ing|ped|ping)?"  # trip → trips, tripping
    return any(
        re.search(rf"(?<![a-z]){re.escape(w.strip())}{suffix}(?![a-z])", text) for w in words
    )


def _product_aliases(tables: RefTables) -> list[tuple[str, str]]:
    aliases: list[tuple[str, str]] = []
    for code, p in tables.products.items():
        aliases.append((code.lower(), code))
        aliases.append((p.name.lower(), code))
        last = code.split("-")[-1]
        if len(last) >= 3 and any(c.isalpha() for c in last):
            aliases.append((last.lower(), code))
    return sorted(aliases, key=lambda a: -len(a[0]))


def classify(inquiry: InquiryIn, llm: LLMRouter) -> Classification:
    if inquiry.category is not None:  # 문의서에서 고객이 고른 값
        return Classification(category=inquiry.category, confidence=1.0, model="form")
    text = f"{inquiry.subject}\n{inquiry.body}"
    if llm.enabled:
        j = llm.judge("classify", f"문의 유형을 고르라.\n\n{text}", [c.value for c in Category])
        return Classification(category=Category(j.answer), confidence=j.confidence, model=j.model)
    lowered = text.lower()
    if ERROR_CODE_RE.search(text):
        return Classification(category=Category.DEFECT, confidence=0.6, model="keyword")
    for category, words in _CATEGORY_KEYWORDS:
        if _has_any(lowered, words):
            return Classification(category=category, confidence=0.6, model="keyword")
    return Classification(category=Category.TECH_SPEC, confidence=0.3, model="keyword")


def extract(inquiry: InquiryIn, tables: RefTables | None = None) -> Extraction:
    tables = tables or load_tables()
    text = f"{inquiry.subject}\n{inquiry.body}"
    lowered = text.lower()

    product_code = inquiry.product_code
    if product_code is None:
        product_code = next((c for alias, c in _product_aliases(tables) if alias in lowered), None)
    product = tables.products.get(product_code) if product_code else None

    error = ERROR_CODE_RE.search(text)
    serial = SERIAL_RE.search(text)
    fw = FW_RE.search(text)
    urgency = next((u for u, words in _URGENCY_KEYWORDS if _has_any(lowered, words)), Urgency.NONE)

    provided = set(inquiry.provided_fields)
    if product:
        provided.add("product_model")
    if error:
        provided.add("error_code")
    if serial:
        provided.add("serial_no")
    if fw:
        provided.add("current_fw")
    # TODO(CSA-26): 수량·인코텀즈·납기일 등 나머지 필수 항목은 Gemini 구조화 출력으로 추출한다.

    return Extraction(
        product_code=product.code if product else None,
        product_family=product.family if product else None,
        error_code=error.group(0) if error else None,
        fw_version=fw.group(1) if fw else None,
        serial_no=serial.group(1) if serial else None,
        urgency=urgency,
        language=inquiry.language,
        provided_info=sorted(provided),
    )
