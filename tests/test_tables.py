import csv
import shutil
from pathlib import Path

import pytest

from cs_agent.config import get_settings
from cs_agent.rules.tables import ALL, Product, audit_tickets, load_tables


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


def test_products_preserve_drafting_reference_values():
    tables = load_tables()
    with (get_settings().ref_dir / "product_master.csv").open(
        encoding="utf-8-sig", newline=""
    ) as f:
        rows = list(csv.DictReader(f))
    for row in rows:
        product = tables.products[row["product_code"]]
        for key in (
            "list_price_usd",
            "std_lead_time_weeks",
            "moq",
            "standards",
            "certifications",
            "warranty_months",
        ):
            assert getattr(product, key) == row[key].strip()
        assert product.doc_ids == tuple(filter(None, row["doc_ids"].split(";")))
    product = tables.products["MCCB-ABS-103c"]
    assert (product.list_price_usd, product.std_lead_time_weeks, product.moq) == ("85", "4", "10")
    assert "(-U variant)" in tables.products["MCCB-ABS-403c"].certifications


def test_old_product_constructor_keeps_missing_values_unconfirmed():
    product = Product("TEST", "Test product", "DRIVE", "AUTOMATION")
    assert product.list_price_usd == product.std_lead_time_weeks == product.moq == ""
    assert product.doc_ids == ()
    assert product.warranty_months == ""


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


def _ref_copy(tmp_path: Path) -> Path:
    ref = tmp_path / "ref"
    shutil.copytree(get_settings().ref_dir, ref)
    return ref


def test_ref_tables_are_hashable() -> None:
    tables = load_tables()

    assert {tables} == {load_tables()}  # set·lru_cache 인자로 쓸 수 있다


def test_row_with_unquoted_comma_names_file_and_line(tmp_path: Path) -> None:
    ref = _ref_copy(tmp_path)
    with (ref / "family_divisions.csv").open("a", encoding="utf-8") as f:
        f.write("SENSOR,AUTOMATION,자동화,기획서 5.2, 확정본\n")

    with pytest.raises(ValueError, match=r"family_divisions\.csv:13: 열 개수"):
        load_tables(ref)


def test_duplicate_key_is_rejected(tmp_path: Path) -> None:
    ref = _ref_copy(tmp_path)
    with (ref / "family_divisions.csv").open("a", encoding="utf-8") as f:
        f.write("DRIVE,POWER,전력,\n")

    with pytest.raises(ValueError, match="family_divisions.csv: 키 DRIVE"):
        load_tables(ref)


def test_duplicate_sla_key_is_rejected(tmp_path: Path) -> None:
    ref = _ref_copy(tmp_path)
    path = ref / "sla_policy.csv"
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    path.write_text("\n".join([*lines, lines[1]]) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="sla_policy.csv: 키"):
        load_tables(ref)


def test_request_labels_cover_required_fields_in_plain_words() -> None:
    tables = load_tables()
    required = {f for fields, _ in tables.required.values() for f in fields}

    assert required <= set(tables.request_labels)  # 묻는 항목은 모두 쉬운 이름이 있다
    assert set(tables.request_labels) <= set(tables.field_labels)
    assert "nameplate" in tables.request_labels["serial_no"]
    # 원본 라벨(고객 문의서·분석 CSA-26 이 쓰는 형식)은 그대로
    assert tables.field_labels["serial_no"] == "Serial number (nameplate)"
    assert all(
        "\n" not in label and not label[:1].isdigit() for label in tables.request_labels.values()
    )  # 번호 목록 세기를 흐트러뜨리지 않는다
