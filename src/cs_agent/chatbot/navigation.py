# 화면 이동 규칙표 + 화면 이동 에이전트 (CSA-33 · 담당 조수빈 · Sprint 2)
#
# 챗봇 응답에 담겨 고객 화면 대시보드를 움직이는 지시(제품, 탭, 강조 항목)를 정한다.
# AI는 제품·유형·에러코드를 뽑는 데까지만 쓰고(문의 분석 CSA-26), 어느 탭으로 갈지는 규칙표가
#   정한다.
# 같은 질문에는 항상 같은 칸이 열려야 한다.
#
# 할 일
# 1. data/ref/navigation_rules.csv 를 확정한다 (기획서 5.4 표). 열: nav_rule_id, intent, tab,
#      anchor.
#    intent = PRODUCT_ONLY / FAMILY_ONLY / 유형 10개. tab = info | install | faults | firmware |
#      docs | faq | tree.
# 2. decide():
#    - 제품을 모르고 제품군만 알면 → FAMILY_ONLY: 화면은 그대로, candidates 에 그 제품군 제품 코드
#        목록
#      (챗봇이 "제품 선택" 버튼으로 보여준다)
#    - 제품만 알고 유형 확신도가 낮으면 → PRODUCT_ONLY (제품 정보 탭)
#    - 둘 다 알면 → 유형 규칙. anchor 가 error_code 면 추출된 에러코드를 넣는다 (고장 탭에서 그
#        코드 강조)
#    - 아무것도 모르면 → 이동 없음
# 3. 고객이 대시보드에서 직접 다른 제품·탭을 누르면 그 화면이 다음 대화의 맥락이 된다
#    (ChatIn.viewing_product). 이 연동은 chatbot/agent.py 에서 쓴다.
#
# 완료 기준: 기획서 5.4 표의 예 8개("iS7 75kW 알려줘", "S100 가속 중 E.OC" …)가 표대로 이동
#
# 구현 메모
# - anchor 열은 값이 아니라 "무엇을 강조할지의 종류"다. 값을 얻을 수 있는 error_code(추출된 코드)와
#   family(제품군)만 실제 값으로 바꾸고, 나머지(spec_row·section·doc_id·latest·lead_time·policy)는
#   종류 이름을 그대로 넘긴다. 화면(ProductDetail, CSA-37)이 종류에 맞게 강조한다.
#   사양 행·절·문서 id 까지 짚으려면 추출을 넓혀야 하는데 그건 문의 분석(CSA-26) 몫이다.
# - 유형 확신도가 min_confidence 미만이거나 분류가 없으면 제품 정보 탭(PRODUCT_ONLY)이다.
#   기준값 0.5 는 스켈레톤의 기본값이고, 실제 분포로 다시 정하는 일은 평가 단계에서 한다.
# - 기준표에 없는 제품 코드는 모르는 제품으로 본다.
from pydantic import BaseModel, Field

from cs_agent.rules.tables import RefTables, load_tables
from cs_agent.schemas import Classification, Extraction

PRODUCT_ONLY = "PRODUCT_ONLY"
FAMILY_ONLY = "FAMILY_ONLY"


class Navigation(BaseModel):
    """챗봇 응답에 담기는 이동 지시. 화면(frontend/src/api/client.ts)과 같은 모양."""

    product_code: str | None = None
    tab: str | None = None
    anchor: str | None = None
    rule_id: str | None = None
    candidates: list[str] = Field(default_factory=list)


def decide(
    extraction: Extraction,
    classification: Classification | None,
    tables: RefTables | None = None,
    min_confidence: float = 0.5,
) -> Navigation:
    """추출·분류 결과 → 이동 지시. 위 '할 일 2' 참고."""
    tables = tables or load_tables()
    product = tables.products.get(extraction.product_code or "")

    if product is None:
        family = extraction.product_family
        if not family:
            return Navigation()
        candidates = [code for code, p in tables.products.items() if p.family == family]
        if not candidates:
            return Navigation()
        return _move(tables, FAMILY_ONLY, None, family, candidates=candidates)

    confident = classification is not None and classification.confidence >= min_confidence
    intent = str(classification.category) if confident else PRODUCT_ONLY
    if intent not in tables.navigation:
        intent = PRODUCT_ONLY
    return _move(tables, intent, product.code, extraction.error_code)


def _move(
    tables: RefTables,
    intent: str,
    product_code: str | None,
    value: str | None,
    candidates: list[str] | None = None,
) -> Navigation:
    """규칙표 한 줄 → Navigation. value 는 error_code·family 처럼 anchor 가 값을 가질 때의 값."""
    rule = tables.navigation[intent]
    kind = rule["anchor"]
    anchor = value if kind in ("error_code", "family") else kind
    return Navigation(
        product_code=product_code,
        tab=rule["tab"],
        anchor=anchor or None,
        rule_id=rule["nav_rule_id"],
        candidates=candidates or [],
    )
