# 에이전트 사이 · API 입출력 데이터 모델 (CSA-21 · 담당 김동규 · Sprint 1)
#
# pydantic BaseModel 로 만든다. 에이전트 담당자들은 이 모양에 맞춰 입출력을 만든다.
# 화면 쪽 타입(frontend/src/api/client.ts)과 이름을 맞춘다. 바꿀 때는 팀에 알린다.
#
# 1. InquiryIn (① 접수, 5개 채널 공통 형식, C-01)
#    channel, customer_id, customer_tier(STANDARD|GOLD|PLATINUM), country, language, subject, body,
#    product_code(문의서·챗봇이 미리 채운 값), category(고객이 고른 유형), provided_fields(dict),
#    thread_ref(메일 스레드 등 후속 문의 연결 키), received_at
# 2. Classification (② 분류): category, secondary_category, confidence, model
# 3. Extraction (③ 추출): product_code(None = 미확인), product_family, error_code, fw_version,
#    serial_no, urgency(Urgency), language, provided_info(list[str], required_info.csv 의 항목 이름)
# 4. Evidence (④⑧ 검색 근거): source(docs|cases), doc_id, section, text, score
# 5. RuleResult (⑤ 규칙 처리): priority, priority_rule_id, assigned_dept, routing_rule_id,
#      escalate_to,
#    required_info, missing_info, missing_blocking, sla_first_response_h, sla_resolution_h, sla_id
# 6. Draft (⑨ 답변): text, template, slots(dict), cited(list "doc_id#section"), model
# 7. CheckResult (⑩ 자동 점검): name, passed, reason
# 8. ReviewIn (상담원 버튼 입력, 그래프 resume 값): action(ReviewAction), reviewer, edited_text,
#    feedback(한 줄), feedback_reason(FeedbackReason), escalate_to, info_items(요청할 항목)
# 9. TicketOut (API 응답): ticket_id, status, route, category, product_code, priority,
#      assigned_dept,
#    sla_due_at, draft, info_request, checks, evidence
