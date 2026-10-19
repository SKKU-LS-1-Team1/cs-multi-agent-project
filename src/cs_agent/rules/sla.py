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
#    TODO(CSA-40): 아직 없음. 작업 목록(services/tickets.py work_list)이 아래 함수로 매번 계산한다.
#
# 완료 기준: tickets 의 sla_first_response_target_h / sla_resolution_target_h 와 100% 일치
from dataclasses import dataclass
from datetime import datetime, timedelta

from cs_agent.domain import Category
from cs_agent.rules.tables import RefTables, load_tables

DEFAULT_TIER = "STANDARD"  # 고객 등급을 모르면


@dataclass(frozen=True)
class SlaTarget:
    sla_id: str
    first_response_h: float
    resolution_h: float


def sla_targets(
    category: Category, tier: str, priority: str, tables: RefTables | None = None
) -> SlaTarget:
    tables = tables or load_tables()
    row = tables.sla.get((str(category), tier or DEFAULT_TIER, priority))
    if row is None:
        row = tables.sla[(str(category), DEFAULT_TIER, priority)]
    return SlaTarget(
        sla_id=row["sla_id"],
        first_response_h=float(row["first_response_hours"]),
        resolution_h=float(row["resolution_hours"]),
    )


def elapsed_hours(received_at: datetime, now: datetime, customer_wait_h: float = 0.0) -> float:
    """24x7 달력 시간으로 경과 − 고객 회신 대기(WAITING_CUSTOMER) 시간"""
    hours = (now - received_at).total_seconds() / 3600 - customer_wait_h
    return max(hours, 0.0)


def due_at(received_at: datetime, target_h: float, customer_wait_h: float = 0.0) -> datetime:
    return received_at + timedelta(hours=target_h + customer_wait_h)


def is_at_risk(elapsed_h: float, target_h: float) -> bool:
    from cs_agent.config import get_settings

    if target_h <= 0:
        return True
    return elapsed_h / target_h >= get_settings().sla_at_risk_ratio
