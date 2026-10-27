# 테스트용 분석 에이전트 대역 (그래프·API 흐름 테스트에서 LLM 없이 ②③ 자리를 채운다)
#
# 실제 구현은 agents/analysis.py. 여기 함수는 tests/ 밖에서 쓰지 않는다.
import re

from cs_agent.domain import Urgency
from cs_agent.rules.engine import UNKNOWN_PRODUCT_FIELD
from cs_agent.schemas import Classification, Extraction, InquiryIn

_SAFETY = re.compile(r"(?i)\b(smoke|fire|spark(?:s|ing)?)\b|연기|화재|감전")


def classify(inquiry: InquiryIn, llm) -> Classification:
    assert inquiry.category, "테스트 문의는 category 를 채워 둔다"
    return Classification(category=inquiry.category, confidence=1.0, model="stub")


def extract(inquiry: InquiryIn, tables, *, llm=None, category=None) -> Extraction:
    text = f"{inquiry.subject}\n{inquiry.body}"
    code = inquiry.product_code or next(
        (c for c in tables.products if re.search(rf"\b{re.escape(c)}\b", text)), None
    )
    product = tables.products.get(code) if code else None
    provided = list(inquiry.provided_fields)
    if product:
        provided.append(UNKNOWN_PRODUCT_FIELD)
    return Extraction(
        product_code=product.code if product else None,
        product_family=product.family if product else None,
        urgency=Urgency.SAFETY if _SAFETY.search(text) else Urgency.NONE,
        language=inquiry.language,
        provided_info=provided,
    )


def pass_customer_qc(text, *args, **kwargs):
    import hashlib

    from cs_agent.qc_schemas import QcResult

    return QcResult(decision="PASS", text_hash=hashlib.sha256(text.encode()).hexdigest())


ANALYSIS = {"classify": classify, "extract": extract, "check_customer_qc": pass_customer_qc}
