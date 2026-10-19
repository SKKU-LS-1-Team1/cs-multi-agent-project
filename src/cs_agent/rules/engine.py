"""⑤ 규칙 처리 노드 (CSA-22 · 담당 김동규).

우선순위·담당 부서·필수정보·누락 항목을 기준표로 정한다. 모든 결과에 rule_id를 남긴다 (N-04).
"""

from cs_agent.domain import Category, Urgency
from cs_agent.rules.sla import sla_targets
from cs_agent.rules.tables import RefTables, load_tables
from cs_agent.schemas import Classification, Extraction, RuleResult

FALLBACK_DEPT = "GCS_L1"


def decide_priority(
    category: Category, urgency: Urgency, tables: RefTables | None = None
) -> tuple[str, str]:
    """priority_rules.csv를 위에서부터 보고 처음 맞는 규칙을 쓴다."""
    tables = tables or load_tables()
    for rule in tables.priority:
        if rule["urgency_flag"] != urgency.value:
            continue
        cats = rule["categories"]
        if cats == "*" or category.value in cats.split(";"):
            return rule["priority"], rule["priority_rule_id"]
    return "P3", "PR-DEFAULT"


def route_department(
    family: str | None, category: Category, tables: RefTables | None = None
) -> tuple[str, str]:
    tables = tables or load_tables()
    hit = tables.routing.get((family or "", category.value))
    if hit is None:
        # TODO(CSA-22): 제품 미확인 문의의 기본 라우팅 규칙을 기준표로 옮긴다.
        return "RT-DEFAULT", FALLBACK_DEPT
    return hit


def required_info(
    family: str | None, category: Category, tables: RefTables | None = None
) -> tuple[list[str], list[str]]:
    tables = tables or load_tables()
    hit = tables.required.get((family or "", category.value))
    if hit is None:
        # 제품군을 모르면 같은 유형의 아무 제품군 규칙을 쓴다 (모든 유형에 product_model 포함).
        hit = next(
            (v for (_, cat), v in tables.required.items() if cat == category.value),
            (["product_model"], ["product_model"]),
        )
    return hit


def apply_rules(
    classification: Classification,
    extraction: Extraction,
    customer_tier: str,
    tables: RefTables | None = None,
) -> RuleResult:
    tables = tables or load_tables()
    category = classification.category
    priority, priority_rule = decide_priority(category, extraction.urgency, tables)
    rule_id, dept = route_department(extraction.product_family, category, tables)
    required, blocking = required_info(extraction.product_family, category, tables)
    provided = set(extraction.provided_info)
    missing = [k for k in required if k not in provided]
    sla = sla_targets(category, customer_tier, priority, tables)
    return RuleResult(
        priority=priority,
        priority_rule_id=priority_rule,
        assigned_dept=dept,
        routing_rule_id=rule_id,
        escalate_to=None,  # TODO(CSA-22): 이관 규칙 (예: RETURN 비불량 → SCM)
        required_info=required,
        missing_info=missing,
        missing_blocking=[k for k in missing if k in blocking],
        sla_first_response_h=sla.first_response_h,
        sla_resolution_h=sla.resolution_h,
        sla_id=sla.sla_id,
    )
