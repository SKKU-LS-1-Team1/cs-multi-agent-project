# 문의 처리 서비스 (CSA-21 · CSA-25 · 담당 김동규)
#
# API 와 그래프 사이. 그래프 실행·재개, 저장소 기록을 묶는다. class TicketService 로 만든다.
#
# 만들 메서드
# 1. submit(inquiry: InquiryIn) -> TicketOut
#    ticket_id 발급 → tickets 행 저장 → graph.invoke({"ticket_id", "inquiry"}, {"configurable":
#      {"thread_id": ticket_id}})
#    → 상담원 검토 지점에서 멈춘 상태로 TicketOut 반환
# 2. act(ticket_id, review: ReviewIn) -> TicketOut  (CSA-25)
#    graph.invoke(Command(resume=review.model_dump(mode="json")), config)
#    reviews 테이블에 기록: action, 원본(직전 draft), 수정본(edited_text), 피드백 한 줄, 수정 사유
#    재작성이면 drafts 에 새 버전 행
# 3. resolve(ticket_id) -> TicketOut
#    상태 RESOLVED, 해결 시각 기록. 마지막 상담원 행동이 저장 대상이면 사례 DB 저장
#    (agents/case_memory.py SAVE_ON, build_case)
# 4. get(ticket_id) -> TicketOut: graph.get_state(config).values 로 만든다. sla_due_at =
#      rules/sla.py due_at
# 5. work_list(dept=None) -> list[dict]  (CSA-40)
#    열린 티켓을 SLA 경과 비율 큰 순으로, at_risk(≥ 75%) 표시. DB가 붙으면 db/sql/work_list.sql 로.
#
# 저장소: 처음엔 메모리(dict)로 시작해도 되고, 조수빈 님 스키마(CSA-24)가 오면 PostgreSQL 로 바꾼다.
