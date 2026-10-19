from cs_agent.rules.tables import ALL, audit_tickets, load_tables


def test_load_tables_reads_reference_files() -> None:
    tables = load_tables()

    assert tables is load_tables()  # lru_cache
    assert len(tables.products) == 23
    assert tables.routing[(ALL, "RETURN")]["rule_id"] == "RT-ALL-RETURN-NON_DEFECT"
    assert {row["rule_id"] for row in tables.escalation} == {
        "RT-ESC-DEFECT-RMA",
        "RT-ESC-DEFECT-ONSITE",
        "RT-ESC-DEFECT-SAFETY",
    }
    assert tables.field_labels["serial_no"] == "Serial number (nameplate)"
    assert "SAFETY" in tables.urgency
    assert tables.departments["GCS_L1"]["level"] == "L1"
    assert len(tables.customers) == 600
    assert tables.spec_facts["MCCB-ABS-103c"]
    assert len(tables.faults) == 97
    assert tables.firmware["ACB-AS-2000"][-1]["is_latest"] == "Y"


def test_every_product_has_division() -> None:
    tables = load_tables()

    assert set(tables.divisions) == {"POWER", "AUTOMATION", "ENERGY"}
    assert set(tables.family_divisions) == {p.family for p in tables.products.values()}
    assert all(product.division for product in tables.products.values())
    assert tables.products["INV-LSLV0075-S100"].division == "AUTOMATION"


def _ticket(**overrides: str) -> dict[str, str]:
    row = {
        "ticket_id": "T-1",
        "product_code": "TRF-OIL-1000",
        "product_family": "TRANSFORMER",
        "category_code": "TECH_SPEC",
        "urgency_flag": "NONE",
        "customer_tier": "GOLD",
        "routing_rule_id": "RT-TRANSFORMER-TECH_SPEC",
        "assigned_dept": "TS_TRF",
        "priority_rule_id": "PR-07",
        "priority": "P4",
        "priority_adjusted_by_agent": "N",
        "required_info": "product_model;application",
        "provided_info": "product_model",
        "missing_info": "application",
        "missing_blocking_info": "",
    }
    return {**row, **overrides}


def test_audit_tickets_uses_engine_and_separates_agent_adjustment() -> None:
    report = audit_tickets(
        [_ticket(), _ticket(ticket_id="T-2", priority="P3", priority_adjusted_by_agent="Y")]
    )

    assert report.total == 2
    assert report.routing_match == report.dept_match == report.priority_rule_match == 2
    assert report.required_match == report.missing_match == report.missing_blocking_match == 2
    assert report.priority_match == 1
    assert report.priority_diff_adjusted == 1
    assert report.priority_diff_unexplained == 0


def test_audit_tickets_routes_non_defect_return() -> None:
    ticket = _ticket(
        category_code="RETURN",
        routing_rule_id="RT-ALL-RETURN-NON_DEFECT",
        assigned_dept="SCM",
        priority_rule_id="PR-05",
        priority="P3",
    )

    report = audit_tickets([ticket])

    assert report.non_defect_returns == 1
    assert report.routing_match == report.dept_match == 1
    assert "routing" not in report.mismatches
