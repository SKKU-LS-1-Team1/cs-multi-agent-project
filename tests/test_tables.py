from cs_agent.rules.tables import audit_tickets, find_priority_rule, find_routing, load_tables


def test_load_tables_reads_reference_files() -> None:
    tables = load_tables()

    assert tables is load_tables()  # lru_cache
    assert len(tables.products) == 23
    assert len(tables.routing) == 108
    assert [rule["rule_id"] for rule in tables.priority] == [f"PR-0{i}" for i in range(1, 8)]
    assert {row["rule_id"] for row in tables.escalation} == {
        "RT-ESC-DEFECT-RMA",
        "RT-ESC-DEFECT-ONSITE",
        "RT-ESC-DEFECT-SAFETY",
    }
    assert tables.navigation["DEFECT"]["tab"] == "faults"
    assert tables.required[("LV_BREAKER", "TECH_SPEC")] == (
        ["product_model", "application"],
        ["product_model"],
    )


def test_every_product_has_division() -> None:
    tables = load_tables()

    assert set(tables.divisions) == {"POWER", "AUTOMATION", "ENERGY"}
    assert len({product.family for product in tables.products.values()}) == 11
    assert tables.products["INV-LSLV0075-S100"].division == "AUTOMATION"
    assert tables.products["ESS-BMS-V3"].attrs["tech_support_dept"]


def test_find_routing_applies_rule_source_priority() -> None:
    tables = load_tables()

    assert find_routing(tables, "DRIVE", "RETURN")["rule_id"] == "RT-DRIVE-RETURN"
    non_defect = find_routing(tables, "DRIVE", "RETURN", subtype="NON_DEFECT")
    assert non_defect["rule_id"] == "RT-ALL-RETURN-NON_DEFECT"
    assert non_defect["primary_dept"] == "SCM"
    assert find_routing(tables, None, "RETURN", subtype="NON_DEFECT") == non_defect
    assert find_routing(tables, "MV_EQUIP", "INSTALL")["primary_dept"] == "FIELD_SVC"
    assert find_routing(tables, None, "TECH_SPEC") is None


def test_find_priority_rule_takes_first_match() -> None:
    tables = load_tables()

    assert find_priority_rule(tables, "QUOTE", "SAFETY")["rule_id"] == "PR-01"
    assert find_priority_rule(tables, "DEFECT", "SITE_DOWN")["rule_id"] == "PR-02"
    assert find_priority_rule(tables, "RETURN", "SITE_DOWN")["rule_id"] == "PR-03"
    assert find_priority_rule(tables, "TECH_SPEC", "COMMISSION")["rule_id"] == "PR-04"
    assert find_priority_rule(tables, "ORDER_LEAD", "DEADLINE")["rule_id"] == "PR-05"
    assert find_priority_rule(tables, "MANUAL", "DEADLINE")["rule_id"] == "PR-06"
    rule = find_priority_rule(tables, "TECH_SPEC", "NONE")
    assert (rule["rule_id"], rule["priority"]) == ("PR-07", "P4")


def test_audit_tickets_separates_agent_adjustment() -> None:
    ticket = {
        "ticket_id": "T-1",
        "product_family": "TRANSFORMER",
        "category_code": "TECH_SPEC",
        "urgency_flag": "NONE",
        "routing_rule_id": "RT-TRANSFORMER-TECH_SPEC",
        "assigned_dept": "TS_TRF",
        "priority_rule_id": "PR-07",
        "priority": "P3",
        "priority_adjusted_by_agent": "Y",
        "required_info": "product_model;application",
        "missing_info": "application",
        "missing_blocking_info": float("nan"),
    }

    report = audit_tickets(load_tables(), [ticket])

    assert report.routing_match == report.dept_match == report.priority_rule_match == 1
    assert report.priority_match == 0
    assert report.priority_diff_adjusted == 1
    assert report.priority_diff_unexplained == 0
