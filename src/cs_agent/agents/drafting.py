"""⑨ 답변 작성 에이전트 (CSA-29 정보 안내형 · CSA-30 유형별 확장 · 담당 김도연).

노드 1개 + 유형별 틀 10개. 틀마다 필수 슬롯이 있고, 슬롯 값(사양값·가격·보증기간 등)은
코드가 기준표에서 채워 넘긴다. LLM은 문장만 쓴다. 숫자를 LLM이 만들지 않는다.
"""

from dataclasses import dataclass

from cs_agent.domain import BUNDLE_OF, Bundle, Category
from cs_agent.llm.router import LLMRouter
from cs_agent.rules.tables import load_tables
from cs_agent.schemas import Draft, Evidence, Extraction


@dataclass(frozen=True)
class Template:
    name: str
    required_slots: tuple[str, ...]
    guide: str


MODE_GUIDE = {
    Bundle.INFO: "고객에게 그대로 보낼 수 있는 완성 답변을 쓴다.",
    Bundle.DIAGNOSIS: "원인을 단정하지 말고 원인 후보·점검 순서·추가로 받을 자료를 쓴다. "
    "원격 해결이 안 되면 현장 점검·수리 접수를 제안한다.",
    Bundle.POLICY: "보증기간 내 여부·필요 서류·정책 조항을 정리한다. 승인·반려를 쓰지 않는다.",
}

# TODO(CSA-30): 문서·영업·수리 유형 틀의 슬롯과 문장 가이드를 채운다.
TEMPLATES: dict[Category, Template] = {
    Category.TECH_SPEC: Template(
        "tech_spec", ("product_name", "reference"), "요청한 사양 값과 근거 절"
    ),
    Category.MANUAL: Template("manual", ("product_name", "reference"), "해당 문서와 언어판 안내"),
    Category.COMPLIANCE: Template("compliance", ("product_name", "reference"), "보유 인증, 대안"),
    Category.QUOTE: Template(
        "quote",
        ("product_name", "unit_price", "quantity", "total", "lead_time", "valid_until"),
        "예산 견적: 단가·수량·합계·납기·유효기간",
    ),
    Category.ORDER_LEAD: Template("order_lead", ("product_name", "lead_time"), "출하 예정일"),
    Category.DEFECT: Template("defect", ("product_name", "reference"), "원인 후보와 점검 순서"),
    Category.INSTALL: Template("install", ("product_name", "reference"), "설치 조건과 절차"),
    Category.FW_UPDATE: Template("fw_update", ("product_name", "reference"), "최신 버전, 절차"),
    Category.WARRANTY: Template("warranty", ("product_name", "warranty_period"), "보증 판단 재료"),
    Category.RETURN: Template("return", ("product_name", "reference"), "반품 절차·필요 서류"),
}


def build_slots(extraction: Extraction, evidence: list[Evidence]) -> dict[str, str]:
    """⑧ 근거 확정에서 코드로 채우는 값. TODO(CSA-19): 사양표·정가·납기·보증기간 조회."""
    slots: dict[str, str] = {}
    product = load_tables().products.get(extraction.product_code or "")
    if product:
        slots["product_name"] = product.name
    docs = [e for e in evidence if e.source == "docs"]
    if docs:
        slots["reference"] = f"{docs[0].doc_id} {docs[0].section or ''}".strip()
    return slots


def write_draft(
    category: Category,
    extraction: Extraction,
    evidence: list[Evidence],
    inquiry_text: str,
    llm: LLMRouter,
    fix_notes: list[str] | None = None,
    reviewer_feedback: str | None = None,
) -> Draft:
    template = TEMPLATES[category]
    slots = build_slots(extraction, evidence)
    cited = [f"{e.doc_id}#{e.section}" for e in evidence if e.source == "docs"]
    if llm.enabled:
        sources = "\n\n".join(f"[{e.doc_id} {e.section}] {e.text}" for e in evidence)
        prompt = (
            f"{MODE_GUIDE[BUNDLE_OF[category]]}\n틀: {template.guide}\n"
            f"고객 언어: {extraction.language}\n슬롯 값(그대로 쓸 것): {slots}\n"
            f"근거:\n{sources}\n\n문의:\n{inquiry_text}\n"
            + (f"\n지난 점검 실패 사유: {fix_notes}" if fix_notes else "")
            + (f"\n상담원 지적: {reviewer_feedback}" if reviewer_feedback else "")
        )
        text = llm.write("draft", prompt)
        return Draft(text=text, template=template.name, slots=slots, cited=cited, model="gemini")

    excerpt = evidence[0].text[:400] if evidence else "(근거 문서를 찾지 못했다)"
    text = (
        f"Thank you for your inquiry about {slots.get('product_name', 'our product')}.\n\n"
        f"{excerpt}\n\nReference: {slots.get('reference', '-')}"
    )
    return Draft(text=text, template=template.name, slots=slots, cited=cited, model="template")
