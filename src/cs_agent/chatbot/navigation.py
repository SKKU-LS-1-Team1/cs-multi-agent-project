"""화면 이동 규칙표 + 화면 이동 에이전트 (CSA-33 · 담당 조수빈).

AI는 제품·유형·에러코드를 뽑는 데까지만 쓰고, 어느 탭·항목으로 갈지는 규칙표가 정한다.
제품을 확신하지 못하면 화면을 옮기지 않고 후보 제품을 버튼으로 보여준다.
"""

from pydantic import BaseModel, Field

from cs_agent.rules.tables import RefTables, load_tables
from cs_agent.schemas import Classification, Extraction


class Navigation(BaseModel):
    product_code: str | None = None
    tab: str | None = None  # info | install | faults | firmware | docs | faq | tree
    anchor: str | None = None
    rule_id: str | None = None
    candidates: list[str] = Field(default_factory=list)


def decide(
    extraction: Extraction,
    classification: Classification | None,
    tables: RefTables | None = None,
    min_confidence: float = 0.5,
) -> Navigation:
    tables = tables or load_tables()
    if extraction.product_code is None:
        if extraction.product_family:
            rule = tables.navigation["FAMILY_ONLY"]
            candidates = [
                p.code for p in tables.products.values() if p.family == extraction.product_family
            ]
            return Navigation(tab=rule["tab"], rule_id=rule["nav_rule_id"], candidates=candidates)
        return Navigation()
    intent = "PRODUCT_ONLY"
    if classification and classification.confidence >= min_confidence:
        intent = classification.category.value
    rule = tables.navigation.get(intent, tables.navigation["PRODUCT_ONLY"])
    anchor = extraction.error_code if rule["anchor"] == "error_code" else rule["anchor"] or None
    return Navigation(
        product_code=extraction.product_code,
        tab=rule["tab"],
        anchor=anchor,
        rule_id=rule["nav_rule_id"],
    )
