# SLA 계산 (CSA-22 · 담당 김동규) — 작업 목록 정렬·75% 경고(CSA-40)도 이 함수를 쓴다.
#
# sla_policy.csv: 첫 응답은 등급 × 우선순위, 해결은 기본값 × 유형 계수(WARRANTY 1.5,
#   ORDER_LEAD·MANUAL 0.5,
# RETURN 2.0, 나머지 1.0)로 이미 풀려 있다. 시계는 24x7 달력 시간.
#
# 할 일
# 1. sla_targets(category, tier, priority): sla_policy.csv 행 → SlaTarget.
# 2. elapsed_hours(): 경과 시간 − 고객 회신 대기 시간(WAITING_CUSTOMER 동안). 대기 시간은
#    tickets.customer_wait_hours 에 누적한다 (DB, CSA-24).
# 3. due_at(): 접수 시각 + 목표 시간 + 대기 시간.
# 4. is_at_risk(): 경과 / 목표 ≥ settings.sla_at_risk_ratio (0.75).
# 5. 그래프 밖 SLA 감시 작업(주기 실행): 남은 시간 정렬, 75% 경고, 재문의 2회 팀장 알림,
#    이관 건(해결 시간 2배)을 더 일찍 표시. 스케줄러 위치는 정해서 여기 적는다.
#
# 완료 기준: tickets 의 sla_first_response_target_h / sla_resolution_target_h 와 100% 일치
#
# 만들 것 (이름·모양은 다른 파일이 이대로 부른다)
#
#   @dataclass(frozen=True)
#   class SlaTarget:
#       sla_id: str
#       first_response_h: float
#       resolution_h: float
#
#   def sla_targets(
#       category: Category, tier: str, priority: str, tables: RefTables | None = None
#   ) -> SlaTarget:
#
#   def elapsed_hours(received_at: datetime, now: datetime, customer_wait_h: float = 0.0) -> float:
#
#   def due_at(received_at: datetime, target_h: float, customer_wait_h: float = 0.0) -> datetime:
#
#   def is_at_risk(elapsed_h: float, target_h: float) -> bool:
