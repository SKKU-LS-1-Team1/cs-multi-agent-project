"""SLA 기한 계산 (CSA-22) · SLA 감시 작업 (CSA-40 작업 목록 정렬·75% 경고).

sla_policy.csv: first_response는 등급×우선순위, resolution은 기본값×유형 계수로 이미 풀려 있다.
고객 회신 대기(WAITING_CUSTOMER) 시간은 경과 시간에서 뺀다.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from cs_agent.config import get_settings
from cs_agent.domain import Category
from cs_agent.rules.tables import RefTables, load_tables


@dataclass(frozen=True)
class SlaTarget:
    sla_id: str
    first_response_h: float
    resolution_h: float


def sla_targets(
    category: Category, tier: str, priority: str, tables: RefTables | None = None
) -> SlaTarget:
    tables = tables or load_tables()
    row = tables.sla.get((category.value, tier, priority))
    if row is None:
        row = tables.sla[(category.value, "STANDARD", priority)]
    return SlaTarget(
        sla_id=row["sla_id"],
        first_response_h=float(row["first_response_hours"]),
        resolution_h=float(row["resolution_hours"]),
    )


def elapsed_hours(received_at: datetime, now: datetime, customer_wait_h: float = 0.0) -> float:
    """24x7 달력 시간 기준 경과 시간에서 고객 대기 시간을 뺀다."""
    return max(0.0, (now - received_at).total_seconds() / 3600 - customer_wait_h)


def due_at(received_at: datetime, target_h: float, customer_wait_h: float = 0.0) -> datetime:
    return received_at + timedelta(hours=target_h + customer_wait_h)


def sla_ratio(elapsed_h: float, target_h: float) -> float:
    return elapsed_h / target_h if target_h else 1.0


def is_at_risk(elapsed_h: float, target_h: float) -> bool:
    return sla_ratio(elapsed_h, target_h) >= get_settings().sla_at_risk_ratio
