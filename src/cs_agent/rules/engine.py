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
#
# 만들 것 (이름·모양은 다른 파일이 이대로 부른다)
#
#   def decide_priority(
#       category: Category, urgency: Urgency, tables: RefTables | None = None
#   ) -> tuple[str, str]:
#       """→ (priority, priority_rule_id)"""
#
#   def route_department(
#       family: str | None, category: Category, tables: RefTables | None = None
#   ) -> tuple[str, str]:
#       """→ (routing_rule_id, assigned_dept)"""
#
#   def required_info(
#       family: str | None, category: Category, tables: RefTables | None = None
#   ) -> tuple[list[str], list[str]]:
#       """→ (필수 항목, 처리 차단 항목)"""
#
#   def apply_rules(
#       classification: Classification,
#       extraction: Extraction,
#       customer_tier: str,
#       tables: RefTables | None = None,
#   ) -> RuleResult:
