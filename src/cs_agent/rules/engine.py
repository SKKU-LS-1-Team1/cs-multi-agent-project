# 규칙 처리 — ⑤ (CSA-22 · 담당 김동규 · Sprint 1)
#
# 그래프의 rules 노드가 부른다. 정답이 정해진 판단이라 LLM이 아니라 코드로 한다 (P-02).
# 결과마다 rule_id 를 남긴다 (N-04 추적성).
#
# 할 일
# 1. decide_priority(category, urgency): priority_rules.csv 를 위에서부터 보고 처음 맞는 규칙.
#    기준표: SAFETY→P1(PR-01), SITE_DOWN+{DEFECT,INSTALL,FW_UPDATE}→P1(PR-02),
#      SITE_DOWN+{ORDER_LEAD,RETURN,WARRANTY}→P2(PR-03), PROD_IMPACT/COMMISSION→P2(PR-04),
#      조치형 유형→P3(PR-05), DEADLINE+정보성→P3(PR-06), 그 외 정보 요청→P4(PR-07).
# 2. route_department(family, category): routing_rules.csv (rule_source 우선순위는 rules/tables.py).
#    제품 미확인이면 기본 부서(GCS_L1) 규칙.
# 3. required_info(family, category): (필수 항목, 차단 항목). 제품군을 모르면 같은 유형의 규칙.
#    chatbot/form_filler.py 와 chatbot/agent.py 도 이 함수를 쓴다.
# 4. apply_rules(): 위 셋 + 누락 항목(필수 − extraction.provided_info) + 차단성 누락 + SLA 목표
#    (rules/sla.py sla_targets) 를 RuleResult 로 묶는다. escalate_to 는 이관 규칙(CSA-19 할 일 4).
# 5. 분기 기준: urgency == SAFETY → 사람 큐, missing_blocking 이 있으면 → 추가정보 요청, 아니면 →
#      답변.
#    이 분기는 graph/builder.py rules 노드에 있다.
#
# 완료 기준
# - valid 603건: 부서 일치 100%(게이트), 우선순위 일치율, 누락 항목 탐지율(K5) 보고
# - 첫 티켓 CSV1-000001 (GOLD·TECH_SPEC·P4) → TS_TRF, SLA 48h/240h
#
# 참고: 기획서 v10 4.2·4.3, analysis/sla_policy/SLA_정책_분석.md
import re

from cs_agent.domain import Category, Urgency
from cs_agent.rules.sla import sla_targets
from cs_agent.rules.tables import ALL, RefTables, load_tables
from cs_agent.schemas import Classification, Extraction, RuleResult

# 제품 미확인일 때 (routing_rules.csv 에 없는 기본 규칙)
DEFAULT_ROUTING_RULE_ID = "RT-DEFAULT"
DEFAULT_DEPT = "GCS_L1"
# 제품을 모르면 제품 모델을 먼저 받아야 한다
UNKNOWN_PRODUCT_FIELD = "product_model"

_WORD = re.compile(r"[A-Z][A-Z_]+")


def _condition_sets(condition: str) -> tuple[set[str], set[str]]:
    """priority_rules.csv condition 글 → (urgency 집합, category 집합). 빈 집합 = 제한 없음."""
    words = set(_WORD.findall(condition))
    return words & {u.value for u in Urgency}, words & {c.value for c in Category}


def decide_priority(
    category: Category, urgency: Urgency, tables: RefTables | None = None
) -> tuple[str, str]:
    """→ (priority, priority_rule_id)"""
    tables = tables or load_tables()
    for rule in tables.priority:
        urgencies, categories = _condition_sets(rule["condition"])
        if urgencies and str(urgency) not in urgencies:
            continue
        if categories and str(category) not in categories:
            continue
        return rule["priority"], rule["rule_id"]
    last = tables.priority[-1]
    return last["priority"], last["rule_id"]


def route_department(
    family: str | None,
    category: Category,
    tables: RefTables | None = None,
    *,
    return_defect: bool | None = None,
) -> tuple[str, str]:
    """→ (routing_rule_id, assigned_dept)

    RETURN 이 불량이 아니면(return_defect=False) SUBTYPE_OVERRIDE(RT-ALL-RETURN-NON_DEFECT).
    """
    tables = tables or load_tables()
    row = None
    if category == Category.RETURN and return_defect is False:
        row = tables.routing.get((ALL, str(category)))
    if row is None and family:
        row = tables.routing.get((family, str(category)))
    if row is None:
        return DEFAULT_ROUTING_RULE_ID, DEFAULT_DEPT
    return row["rule_id"], row["primary_dept"]


def required_info(
    family: str | None, category: Category, tables: RefTables | None = None
) -> tuple[list[str], list[str]]:
    """→ (필수 항목, 처리 차단 항목)

    제품군을 모르면 같은 유형의 모든 제품군에 공통인 항목 + 제품 모델(차단).
    """
    tables = tables or load_tables()
    if family and (family, str(category)) in tables.required:
        required, blocking = tables.required[(family, str(category))]
        return list(required), list(blocking)

    rows = [v for (_, cat), v in tables.required.items() if cat == str(category)]
    if not rows:
        return [UNKNOWN_PRODUCT_FIELD], [UNKNOWN_PRODUCT_FIELD]
    common_req = set.intersection(*(set(r) for r, _ in rows))
    common_blk = set.intersection(*(set(b) for _, b in rows))
    required = [UNKNOWN_PRODUCT_FIELD] + [
        f for f in rows[0][0] if f in common_req and f != UNKNOWN_PRODUCT_FIELD
    ]
    blocking = [UNKNOWN_PRODUCT_FIELD] + [
        f for f in rows[0][1] if f in common_blk and f != UNKNOWN_PRODUCT_FIELD
    ]
    return required, blocking


def apply_rules(
    classification: Classification,
    extraction: Extraction,
    customer_tier: str,
    tables: RefTables | None = None,
) -> RuleResult:
    tables = tables or load_tables()
    category = classification.category
    family = extraction.product_family
    if not family and extraction.product_code in tables.products:
        family = tables.products[extraction.product_code].family

    priority, priority_rule_id = decide_priority(category, extraction.urgency, tables)
    routing_rule_id, dept = route_department(
        family, category, tables, return_defect=extraction.return_defect
    )
    required, blocking = required_info(family, category, tables)
    provided = set(extraction.provided_info)
    missing = [f for f in required if f not in provided]
    sla = sla_targets(category, customer_tier, priority, tables)

    routing_row = next(
        (r for r in tables.routing.values() if r["rule_id"] == routing_rule_id), None
    )
    return RuleResult(
        priority=priority,
        priority_rule_id=priority_rule_id,
        assigned_dept=dept,
        routing_rule_id=routing_rule_id,
        escalate_to=(routing_row or {}).get("escalation_dept") or None,
        required_info=required,
        missing_info=missing,
        missing_blocking=[f for f in missing if f in blocking],
        sla_first_response_h=sla.first_response_h,
        sla_resolution_h=sla.resolution_h,
        sla_id=sla.sla_id,
    )
