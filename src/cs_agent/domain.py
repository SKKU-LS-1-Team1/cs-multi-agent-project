# 도메인 상수 (CSA-21 · 담당 김동규 · Sprint 1) — 팀 전체가 같이 쓰는 값. 바꿀 때는 팀에 알린다.
#
# StrEnum 으로 만든다. 값은 tickets 데이터의 코드 그대로 쓴다.
#
# 1. Category (문의 유형 10개): TECH_SPEC, MANUAL, COMPLIANCE, QUOTE, ORDER_LEAD,
#    DEFECT, INSTALL, FW_UPDATE, WARRANTY, RETURN
# 2. Bundle (기획서 3장 묶음): INFO(정보 안내형), DIAGNOSIS(기술 진단형), POLICY(정책 판단형)
#    BUNDLE_OF: dict[Category, Bundle]
#      INFO      = TECH_SPEC, MANUAL, COMPLIANCE, QUOTE, ORDER_LEAD
#      DIAGNOSIS = DEFECT, INSTALL, FW_UPDATE
#      POLICY    = WARRANTY, RETURN
# 3. Urgency: NONE, SAFETY, SITE_DOWN, PROD_IMPACT, COMMISSION, DEADLINE (tickets.urgency_flag)
# 4. Route (⑥ 분기): human(안전 건 사람 큐), info_request(차단성 누락), draft(정상)
# 5. TicketStatus: NEW, HUMAN_QUEUE, WAITING_CUSTOMER(SLA 정지), READY_FOR_REVIEW, ON_HOLD(점검
#      실패 보류),
#    ESCALATED, APPROVED, REJECTED, RESOLVED
# 6. ReviewAction (관리자 화면 버튼): approve, edit_approve, rewrite(AI 재작성), info_request,
#    escalate(전문부서 이관), reject
# 7. FeedbackReason (기획서 7장 수정 사유): FACT_ERROR, WEAK_EVIDENCE, TONE, ROUTING_ERROR
