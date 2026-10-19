from cs_agent.domain import Category, Urgency
from cs_agent.rules.engine import apply_rules, decide_priority, route_department
from cs_agent.rules.sla import is_at_risk, sla_targets
from cs_agent.schemas import Classification, Extraction


def test_priority_rules():
    assert decide_priority(Category.DEFECT, Urgency.SAFETY) == ("P1", "PR-01")
    assert decide_priority(Category.DEFECT, Urgency.SITE_DOWN) == ("P1", "PR-02")
    assert decide_priority(Category.TECH_SPEC, Urgency.NONE) == ("P4", "PR-07")
    assert decide_priority(Category.RETURN, Urgency.NONE) == ("P3", "PR-05")


def test_routing_and_sla():
    assert route_department("TRANSFORMER", Category.TECH_SPEC) == (
        "RT-TRANSFORMER-TECH_SPEC",
        "TS_TRF",
    )
    # 첫 티켓 CSV1-000001: GOLD · TECH_SPEC · P4 → 48h / 240h
    t = sla_targets(Category.TECH_SPEC, "GOLD", "P4")
    assert (t.first_response_h, t.resolution_h) == (48, 240)
    assert is_at_risk(180, 240) and not is_at_risk(100, 240)


def test_missing_blocking():
    result = apply_rules(
        Classification(category=Category.DEFECT),
        Extraction(
            product_code="INV-LSLV0075-S100",
            product_family="DRIVE",
            provided_info=["product_model"],
        ),
        "STANDARD",
    )
    assert result.assigned_dept == "TS_AUTO"
    assert set(result.missing_blocking) == {"serial_no", "error_code"}
