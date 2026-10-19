"""규칙 처리·SLA (CSA-22) — tickets 데이터의 정답 열과 대조한다.

추출 결과는 tickets 의 정답 열(제품군·긴급도·provided_info)을 그대로 넣는다.
추출 정확도는 CSA-26 에서 따로 잰다.
"""

import csv
from datetime import UTC, datetime

import pytest

from cs_agent.config import get_settings
from cs_agent.domain import Category, Urgency
from cs_agent.rules.engine import (
    DEFAULT_DEPT,
    apply_rules,
    decide_priority,
    required_info,
    route_department,
)
from cs_agent.rules.sla import due_at, elapsed_hours, is_at_risk, sla_targets
from cs_agent.schemas import Classification, Extraction

NON_DEFECT_RETURN = "RT-ALL-RETURN-NON_DEFECT"


def _split(value: str) -> list[str]:
    return [v for v in value.split(";") if v]


@pytest.fixture(scope="module")
def tickets() -> list[dict[str, str]]:
    path = get_settings().raw_data_dir / "tickets.csv"
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _rules_for(row: dict[str, str]):
    category = Category(row["category_code"])
    extraction = Extraction(
        product_code=row["product_code"],
        product_family=row["product_family"],
        urgency=Urgency(row["urgency_flag"]),
        provided_info=_split(row["provided_info"]),
        return_defect=(
            row["routing_rule_id"] != NON_DEFECT_RETURN if category == Category.RETURN else None
        ),
    )
    return apply_rules(Classification(category=category), extraction, row["customer_tier"])


def test_first_ticket():
    # CSV1-000001: GOLD · TECH_SPEC · TRANSFORMER → P4, TS_TRF, SLA 48h/240h
    result = apply_rules(
        Classification(category=Category.TECH_SPEC),
        Extraction(product_code="TRF-OIL-1000", product_family="TRANSFORMER"),
        "GOLD",
    )
    assert (result.priority, result.priority_rule_id) == ("P4", "PR-07")
    assert result.assigned_dept == "TS_TRF"
    assert (result.sla_first_response_h, result.sla_resolution_h) == (48, 240)


def test_valid_set_matches_reference(tickets):
    valid = [t for t in tickets if t["data_split"] == "valid"]
    assert len(valid) == 603
    for row in valid:
        result = _rules_for(row)
        tid = row["ticket_id"]
        assert result.assigned_dept == row["assigned_dept"], tid  # 게이트: 100%
        assert result.routing_rule_id == row["routing_rule_id"], tid
        assert result.priority_rule_id == row["priority_rule_id"], tid
        # 우선순위가 다르면 상담원이 조정한 건이어야 한다
        if result.priority != row["priority"]:
            assert row["priority_adjusted_by_agent"] == "Y", tid
        assert result.required_info == _split(row["required_info"]), tid
        assert set(result.missing_info) == set(_split(row["missing_info"])), tid
        assert set(result.missing_blocking) == set(_split(row["missing_blocking_info"])), tid


def test_sla_targets_match_all_tickets(tickets):
    for row in tickets:
        target = sla_targets(Category(row["category_code"]), row["customer_tier"], row["priority"])
        assert target.first_response_h == float(row["sla_first_response_target_h"])
        assert target.resolution_h == float(row["sla_resolution_target_h"])


@pytest.mark.parametrize(
    ("category", "urgency", "expected"),
    [
        (Category.TECH_SPEC, Urgency.SAFETY, ("P1", "PR-01")),
        (Category.DEFECT, Urgency.SITE_DOWN, ("P1", "PR-02")),
        (Category.RETURN, Urgency.SITE_DOWN, ("P2", "PR-03")),
        (Category.QUOTE, Urgency.COMMISSION, ("P2", "PR-04")),
        (Category.WARRANTY, Urgency.NONE, ("P3", "PR-05")),
        (Category.MANUAL, Urgency.DEADLINE, ("P3", "PR-06")),
        (Category.COMPLIANCE, Urgency.NONE, ("P4", "PR-07")),
    ],
)
def test_decide_priority(category, urgency, expected):
    assert decide_priority(category, urgency) == expected


def test_routing_overrides():
    assert route_department("MV_EQUIP", Category.INSTALL)[1] == "FIELD_SVC"
    assert route_department("PLC", Category.RETURN) == ("RT-PLC-RETURN", "WARRANTY_DESK")
    assert route_department("PLC", Category.RETURN, return_defect=False) == (
        NON_DEFECT_RETURN,
        "SCM",
    )
    assert route_department(None, Category.DEFECT)[1] == DEFAULT_DEPT


def test_unknown_family_asks_for_product_model():
    required, blocking = required_info(None, Category.DEFECT)
    assert required[0] == "product_model"
    assert "product_model" in blocking
    assert "serial_no" in required


def test_sla_clock():
    received = datetime(2025, 10, 1, tzinfo=UTC)
    now = datetime(2025, 10, 3, tzinfo=UTC)  # 48h 경과
    assert elapsed_hours(received, now, customer_wait_h=12) == 36
    assert due_at(received, 48, customer_wait_h=12) == datetime(2025, 10, 3, 12, tzinfo=UTC)
    assert is_at_risk(36, 48)  # 75%
    assert not is_at_risk(35, 48)
