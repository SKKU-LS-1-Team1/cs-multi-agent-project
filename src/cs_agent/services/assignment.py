# 담당 부서·담당자 자동 배정 + 재배정 (CSA-53 · 담당 김동규 · Sprint 2) — 명세서 S-03
#
# 부서는 규칙 처리(⑤, rules/engine.py)가 routing_rules 로 이미 정한다 (RuleResult.assigned_dept,
# 이관되면 escalated_to). 여기서는 그 부서 안에서 담당 상담원을 고르고, SLA 75% 경고 시 다른
# 상담원에게 넘길 수 있게 한다. 관리자 화면 쪽은 CSA-54 (김도연).
#
# 할 일
# 1. 담당자 명단: data/ref/agents.csv (agent_id, name, dept_code, active, max_open) 를 만들고
#    rules/tables.py 처럼 시작할 때 읽는다. dept_code 는 data/ref/departments.csv 코드.
#    명단이 없거나 부서에 활성 담당자가 없으면 배정하지 않는다 (assignee None, 부서 큐에 남음).
# 2. 자동 배정 assign(): 부서 안 활성 담당자 중 지금 열린 건이 가장 적은 사람.
#    같으면 agent_id 순. max_open 을 넘는 사람은 뺀다. 사람 큐 안전 건(부서 없음)은 배정하지 않는다.
#    언제 부르나: 규칙 처리 직후(부서가 정해진 뒤), 이관(escalate) 직후 — 받은 부서에서 다시 배정.
# 3. 재배정 reassign(): 상담원·관리자가 다른 담당자로 넘긴다. 같은 부서 안만 허용
#    (다른 부서로 보내는 건 이관 ReviewAction.ESCALATE). 사유(reason)를 남긴다.
#    75% 경고(work_list at_risk) 건은 화면에서 "넘기기" 후보를 suggest() 로 보여 준다.
# 4. 저장: tickets.assignee 열 + 배정 이력 테이블 (assignments: ticket_id, from, to, reason, at).
#    db/models.py·Alembic 마이그레이션 추가 (CSA-24 스키마 확장). 메모리 모드(MemoryRecords)도 지원.
# 5. API (api/tickets.py 에 추가):
#    - POST /api/tickets/{ticket_id}/assign  {"assignee": "...", "reason": "..."} → TicketOut
#      없는 담당자·다른 부서 담당자 409
#    - GET  /api/agents?dept=                → 담당자 목록 + 열린 건수 (재배정 선택용)
#    - GET  /api/tickets?dept=&assignee=     → 작업 목록에 담당자 필터·열 추가 (work_list.sql 도)
#    TicketOut 에 assignee 추가 (schemas.py).
#
# 완료 기준
# - 부서가 정해진 문의는 접수 직후 담당자가 정해져 있음 (명단이 있을 때)
# - 75% 경고 건을 같은 부서 다른 담당자로 넘기면 작업 목록·이력에 반영
# - 다른 부서 담당자로 넘기려 하면 409
#
# 참고: 명세서 S-03, db/sql/work_list.sql (부서 = COALESCE(escalated_to, assigned_dept))
#
# 만들 것 (이름·모양은 다른 파일이 이대로 부른다)
#
#   @dataclass(frozen=True)
#   class Agent:
#       agent_id: str
#       name: str
#       dept: str
#       active: bool = True
#       max_open: int = 0          # 0 이면 제한 없음
#
#   def load_agents(path: Path | None = None) -> list[Agent]:
#       """data/ref/agents.csv → 담당자 명단. 파일이 없으면 []."""
#
#   def assign(dept: str | None, open_counts: dict[str, int], agents: list[Agent]) -> str | None:
#       """부서 안에서 열린 건이 가장 적은 활성 담당자 agent_id. 없으면 None."""
#
#   def suggest(ticket_dept: str, current: str | None, open_counts: dict[str, int],
#               agents: list[Agent]) -> list[Agent]:
#       """재배정 후보 (같은 부서, 지금 담당자 제외, 열린 건 적은 순)."""
#
#   def reassign(ticket_dept: str, to: str, agents: list[Agent]) -> Agent:
#       """넘길 담당자 확인. 없거나 다른 부서·비활성이면 ValueError (API 는 409)."""
# TODO(CSA-53): 위 함수 + TicketService.assign(ticket_id, assignee, reason) + API
