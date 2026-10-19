# 기준표 로더 (CSA-19 기준표 정리 · 담당 박종석 · Sprint 1)
#
# 규칙 처리(⑤)·근거 확정(⑧)·자동 점검(⑩)·화면 이동이 모두 여기 표를 읽는다.
# 규칙은 코드가 아니라 파일에 둔다 (N-02). 파일은 data/ref/ 에 있다.
#
# data/ref/ (원본 기준표. 파일 맨 앞에 BOM 이 있으니 encoding="utf-8-sig" 로 읽는다)
# - product_master.csv    제품 23개: 제품군·보증기간·리드타임·MOQ·정가·인증·문서 ID·기술지원 부서
# - routing_rules.csv     (family, category) → primary_dept, escalation_dept, escalation_condition.
#                         rule_source 로 우선순위: SUBTYPE_OVERRIDE(예: RT-ALL-RETURN-NON_DEFECT
#                         → SCM) > FAMILY_OVERRIDE > CATEGORY_DEFAULT. ESCALATION 행은 이관 규칙
# - required_info.csv     (family, category) → required_fields, blocking_fields (';' 로 구분)
# - info_field_codebook.csv 항목 이름 → 고객에게 보일 라벨 (추가정보 요청 문구에 쓴다)
# - priority_rules.csv    PR-01~07. order 순서대로 condition 을 보고 처음 맞는 규칙
# - urgency_codebook.csv  긴급도 코드 설명
# - sla_policy.csv        (category, customer_tier, priority) → 첫 응답·해결 목표 시간
# - departments.csv       부서 코드·이름·레벨·담당 범위
# - customers.csv         고객 600곳의 tier·segment (SLA 등급 조회)
# - product_spec_facts.csv 제품별 사양값 + 근거 문서·절 (답변 슬롯, 근거 확정 ⑧)
# - fault_catalog.csv     에러코드 97건: 증상·원인·진단·조치·현장 출동·RMA 여부
# - firmware_history.csv  제품별 펌웨어 버전·출시일·최신 여부·변경 내용
# - reference_master.xlsx 위 표들을 한 파일로 묶은 엑셀 (같은 내용)
# - navigation_rules.csv  기획서 5.4 표 (CSA-33). 원본에 없어 직접 만든 표
# - family_divisions.csv  제품군 → 대분류(전력·자동화·에너지). 원본에 없어 직접 만든 표 (가정,
#                         기획서 5.2 확정본으로 맞춘다)
#
# 검수 (tickets 와 대조): uv run --extra data python -m cs_agent.rules.tables

from __future__ import annotations

import csv
import re
import sys
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
# config.Settings.ref_dir 가 생기면(CSA-21) 그 값을 기본값으로 쓴다.
DEFAULT_REF_DIR = PROJECT_ROOT / "data" / "ref"
RAW_TICKETS_PATH = PROJECT_ROOT / "data" / "raw" / "cs_tickets_resolution_v1.xlsx"

ALL_FAMILIES = "ALL"
# 숫자가 작을수록 먼저 적용된다. ESCALATION 은 부서 배정이 아니라 이관 규칙이라 따로 둔다.
RULE_SOURCE_RANK = {"SUBTYPE_OVERRIDE": 0, "FAMILY_OVERRIDE": 1, "CATEGORY_DEFAULT": 2}
ESCALATION_SOURCE = "ESCALATION"
# priority_rules.csv PR-06 의 "정보성 Category" (domain.BUNDLE_OF 의 INFO 묶음과 같다)
INFO_CATEGORIES = frozenset({"TECH_SPEC", "MANUAL", "COMPLIANCE", "QUOTE", "ORDER_LEAD"})


@dataclass(frozen=True)
class Product:
    code: str
    name: str
    family: str
    division: str  # family_divisions.csv (원본에 없음)
    family_name: str = ""
    attrs: dict[str, str] = field(default_factory=dict)  # product_master.csv 의 나머지 열


@dataclass(frozen=True)
class RefTables:
    products: dict[str, Product]
    routing: dict[tuple[str, str], dict[str, str]]  # (family, category) -> 행 (rule_id·dept)
    required: dict[tuple[str, str], tuple[list[str], list[str]]]  # -> (required, blocking)
    priority: list[dict[str, str]]  # order 순. urgency_in·category_in 은 condition 을 풀어 둔 값
    sla: dict[tuple[str, str, str], dict[str, str]]  # (category, tier, priority) -> row
    navigation: dict[str, dict[str, str]]  # intent -> row (CSA-33)
    escalation: list[dict[str, str]] = field(default_factory=list)  # ESCALATION 행
    divisions: dict[str, str] = field(default_factory=dict)  # division -> 표시 이름
    family_divisions: dict[str, str] = field(default_factory=dict)  # family -> division
    field_labels: dict[str, str] = field(default_factory=dict)  # info_field_codebook
    urgency: dict[str, str] = field(default_factory=dict)  # urgency -> 설명
    departments: dict[str, dict[str, str]] = field(default_factory=dict)
    customers: dict[str, dict[str, str]] = field(default_factory=dict)
    spec_facts: dict[str, list[dict[str, str]]] = field(default_factory=dict)  # product_code ->
    faults: list[dict[str, str]] = field(default_factory=list)
    firmware: dict[str, list[dict[str, str]]] = field(default_factory=dict)  # product_code ->


def _read_csv(ref_dir: Path, name: str, required: Iterable[str]) -> list[dict[str, str]]:
    path = ref_dir / name
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        missing = sorted(set(required) - set(reader.fieldnames or ()))
        if missing:
            raise ValueError(f"{name} is missing required columns: {', '.join(missing)}")
        return [{key: (value or "").strip() for key, value in row.items()} for row in reader]


def _index(rows: list[dict[str, str]], key: str, name: str) -> dict[str, dict[str, str]]:
    indexed: dict[str, dict[str, str]] = {}
    for row in rows:
        if row[key] in indexed:
            raise ValueError(f"{name} has duplicate {key}: {row[key]}")
        indexed[row[key]] = row
    return indexed


def _group(rows: list[dict[str, str]], key: str) -> dict[str, list[dict[str, str]]]:
    grouped: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        grouped.setdefault(row[key], []).append(row)
    return grouped


def _split(value: str) -> list[str]:
    return [item.strip() for item in value.split(";") if item.strip()]


def _subtype(row: dict[str, str]) -> str:
    """SUBTYPE_OVERRIDE 의 하위 유형. RT-ALL-RETURN-NON_DEFECT → NON_DEFECT."""
    if row["rule_source"] != "SUBTYPE_OVERRIDE":
        return ""
    prefix = f"RT-{row['family']}-{row['category']}-"
    if not row["rule_id"].startswith(prefix):
        raise ValueError(f"routing_rules.csv cannot read subtype from {row['rule_id']}")
    return row["rule_id"].removeprefix(prefix)


def _build_routing(
    rows: list[dict[str, str]],
) -> tuple[dict[tuple[str, str], dict[str, str]], list[dict[str, str]]]:
    routing: dict[tuple[str, str], dict[str, str]] = {}
    escalation: list[dict[str, str]] = []
    for row in rows:
        source = row["rule_source"]
        if source == ESCALATION_SOURCE:
            escalation.append(row)
            continue
        if source not in RULE_SOURCE_RANK:
            raise ValueError(f"routing_rules.csv has unknown rule_source: {source}")
        row = {**row, "subtype": _subtype(row)}
        key = (row["family"], row["category"])
        current = routing.get(key)
        if current is None or RULE_SOURCE_RANK[source] < RULE_SOURCE_RANK[current["rule_source"]]:
            routing[key] = row
        elif RULE_SOURCE_RANK[source] == RULE_SOURCE_RANK[current["rule_source"]]:
            raise ValueError(f"routing_rules.csv has two {source} rules for {key}")
    return routing, escalation


def _codes(text: str) -> frozenset[str]:
    return frozenset(code.strip() for code in text.split(",") if code.strip())


def _parse_priority_condition(condition: str) -> tuple[frozenset[str], frozenset[str]]:
    """condition 문장 → (urgency 집합, category 집합). 빈 집합은 '제한 없음'."""
    urgencies: frozenset[str] = frozenset()
    if match := re.search(r"urgency\s*=\s*([A-Z_]+)", condition):
        urgencies = frozenset({match.group(1)})
    elif match := re.search(r"urgency\s*∈\s*\{([^}]*)\}", condition):
        urgencies = _codes(match.group(1))

    categories: frozenset[str] = frozenset()
    if match := re.search(r"Category\s*∈\s*\{([^}]*)\}", condition):
        categories = _codes(match.group(1))
    elif "정보성 Category" in condition:
        categories = INFO_CATEGORIES
    elif match := re.search(r"그 외 정보 요청\s*\(([^)]*)\)", condition):
        categories = _codes(match.group(1))

    if not urgencies and not categories and "모든 Category" not in condition:
        raise ValueError(f"priority_rules.csv condition is not understood: {condition}")
    return urgencies, categories


def _build_priority(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    rules = []
    for row in sorted(rows, key=lambda r: int(r["order"])):
        urgencies, categories = _parse_priority_condition(row["condition"])
        rules.append(
            {
                **row,
                "urgency_in": ";".join(sorted(urgencies)),
                "category_in": ";".join(sorted(categories)),
            }
        )
    return rules


@lru_cache
def load_tables(ref_dir: Path | None = None) -> RefTables:
    """data/ref/*.csv → RefTables. 경로 기본값은 config.Settings.ref_dir."""
    ref_dir = Path(ref_dir) if ref_dir is not None else DEFAULT_REF_DIR

    division_rows = _read_csv(
        ref_dir, "family_divisions.csv", ("family", "division", "division_label")
    )
    family_divisions = {row["family"]: row["division"] for row in division_rows}
    divisions = {row["division"]: row["division_label"] for row in division_rows}

    products: dict[str, Product] = {}
    for row in _read_csv(
        ref_dir, "product_master.csv", ("product_code", "product_name", "family", "family_name")
    ):
        if row["family"] not in family_divisions:
            raise ValueError(f"family_divisions.csv has no division for {row['family']}")
        products[row["product_code"]] = Product(
            code=row["product_code"],
            name=row["product_name"],
            family=row["family"],
            division=family_divisions[row["family"]],
            family_name=row["family_name"],
            attrs=row,
        )

    routing, escalation = _build_routing(
        _read_csv(
            ref_dir,
            "routing_rules.csv",
            ("rule_id", "family", "category", "rule_source", "primary_dept", "escalation_dept"),
        )
    )

    required: dict[tuple[str, str], tuple[list[str], list[str]]] = {}
    for row in _read_csv(
        ref_dir, "required_info.csv", ("family", "category", "required_fields", "blocking_fields")
    ):
        required_fields = _split(row["required_fields"])
        blocking_fields = _split(row["blocking_fields"])
        if not set(blocking_fields) <= set(required_fields):
            raise ValueError(
                f"required_info.csv blocking fields are not required for "
                f"({row['family']}, {row['category']})"
            )
        required[(row["family"], row["category"])] = (required_fields, blocking_fields)

    sla = {
        (row["category"], row["customer_tier"], row["priority"]): row
        for row in _read_csv(
            ref_dir,
            "sla_policy.csv",
            ("sla_id", "category", "customer_tier", "priority", "first_response_hours"),
        )
    }

    return RefTables(
        products=products,
        routing=routing,
        required=required,
        priority=_build_priority(
            _read_csv(ref_dir, "priority_rules.csv", ("rule_id", "order", "condition", "priority"))
        ),
        sla=sla,
        navigation=_index(
            _read_csv(ref_dir, "navigation_rules.csv", ("nav_rule_id", "intent", "tab")),
            "intent",
            "navigation_rules.csv",
        ),
        escalation=escalation,
        divisions=divisions,
        family_divisions=family_divisions,
        field_labels={
            row["field"]: row["label"]
            for row in _read_csv(ref_dir, "info_field_codebook.csv", ("field", "label"))
        },
        urgency={
            row["urgency"]: row["description"]
            for row in _read_csv(ref_dir, "urgency_codebook.csv", ("urgency", "description"))
        },
        departments=_index(
            _read_csv(ref_dir, "departments.csv", ("dept_code", "dept_name_ko")),
            "dept_code",
            "departments.csv",
        ),
        customers=_index(
            _read_csv(ref_dir, "customers.csv", ("customer_id", "tier", "segment")),
            "customer_id",
            "customers.csv",
        ),
        spec_facts=_group(
            _read_csv(ref_dir, "product_spec_facts.csv", ("product_code", "attribute", "value")),
            "product_code",
        ),
        faults=_read_csv(ref_dir, "fault_catalog.csv", ("fault_id", "family", "error_code")),
        firmware=_group(
            _read_csv(ref_dir, "firmware_history.csv", ("product_code", "fw_version", "is_latest")),
            "product_code",
        ),
    )


def find_routing(
    tables: RefTables, family: str | None, category: str, subtype: str | None = None
) -> dict[str, str] | None:
    """rule_source 우선순위대로 부서 배정 규칙을 찾는다.

    subtype 은 분류가 정한 하위 유형이다. RETURN 이 불량이 아니면 "NON_DEFECT" 를 넘긴다.
    맞는 규칙이 없으면 None (제품 미확인 시 기본 부서는 rules/engine.py 가 정한다).
    """
    candidates = [
        row
        for key in ((family, category), (ALL_FAMILIES, category))
        if (row := tables.routing.get(key)) is not None and row["subtype"] in ("", subtype)
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda row: RULE_SOURCE_RANK[row["rule_source"]])


def find_priority_rule(tables: RefTables, category: str, urgency: str) -> dict[str, str]:
    """priority_rules.csv 를 order 순으로 보고 처음 맞는 규칙."""
    for rule in tables.priority:
        if rule["urgency_in"] and urgency not in rule["urgency_in"].split(";"):
            continue
        if rule["category_in"] and category not in rule["category_in"].split(";"):
            continue
        return rule
    raise LookupError(f"no priority rule matches category={category}, urgency={urgency}")


# 검수 — tickets 와 대조해 기준표만으로 정답을 다시 낼 수 있는지 본다.


@dataclass
class AuditReport:
    total: int = 0
    routing_match: int = 0
    dept_match: int = 0
    non_defect_returns: int = 0  # 분류가 subtype=NON_DEFECT 를 넘겨야 맞는 건
    priority_rule_match: int = 0
    priority_match: int = 0
    priority_diff_adjusted: int = 0  # 규칙과 다르지만 상담원 조정(Y)인 건
    priority_diff_unexplained: int = 0
    required_match: int = 0
    blocking_consistent: int = 0
    mismatches: dict[str, list[str]] = field(default_factory=dict)

    def note(self, kind: str, ticket_id: str) -> None:
        self.mismatches.setdefault(kind, []).append(ticket_id)

    def rate(self, count: int) -> str:
        return f"{count}/{self.total} ({count / self.total:.1%})" if self.total else "0/0"


def _text(value: object) -> str:
    if value is None or (isinstance(value, float) and value != value):  # NaN
        return ""
    return str(value).strip()


def audit_tickets(tables: RefTables, tickets: Iterable[Mapping[str, object]]) -> AuditReport:
    report = AuditReport()
    for ticket in tickets:
        report.total += 1
        ticket_id = _text(ticket["ticket_id"])
        family = _text(ticket["product_family"]) or None
        category = _text(ticket["category_code"])
        urgency = _text(ticket["urgency_flag"]) or "NONE"

        # 부서 배정: RETURN 은 불량 여부(subtype)를 분류가 정해야 한다. 여기서는 정답 rule_id 로
        # subtype 을 정하고, 표가 그 규칙과 부서를 다시 낼 수 있는지만 본다.
        expected_rule_id = _text(ticket["routing_rule_id"])
        subtype = None
        if category == "RETURN" and expected_rule_id.endswith("-NON_DEFECT"):
            subtype = "NON_DEFECT"
            report.non_defect_returns += 1
        route = find_routing(tables, family, category, subtype)
        if route is not None and route["rule_id"] == expected_rule_id:
            report.routing_match += 1
        else:
            report.note("routing", ticket_id)
        if route is not None and route["primary_dept"] == _text(ticket["assigned_dept"]):
            report.dept_match += 1
        else:
            report.note("dept", ticket_id)

        rule = find_priority_rule(tables, category, urgency)
        if rule["rule_id"] == _text(ticket["priority_rule_id"]):
            report.priority_rule_match += 1
        else:
            report.note("priority_rule", ticket_id)
        if rule["priority"] == _text(ticket["priority"]):
            report.priority_match += 1
        elif _text(ticket["priority_adjusted_by_agent"]) == "Y":
            report.priority_diff_adjusted += 1
        else:
            report.priority_diff_unexplained += 1
            report.note("priority", ticket_id)

        required, blocking = tables.required.get((family or "", category), ([], []))
        if set(required) == set(_split(_text(ticket["required_info"]))):
            report.required_match += 1
        else:
            report.note("required_info", ticket_id)
        missing = set(_split(_text(ticket["missing_info"])))
        if missing & set(blocking) == set(_split(_text(ticket["missing_blocking_info"]))):
            report.blocking_consistent += 1
        else:
            report.note("blocking", ticket_id)
    return report


def _print_report(split: str, report: AuditReport) -> None:
    print(f"[{split}] tickets={report.total}")
    print(
        f"  routing_rule_id 일치 {report.rate(report.routing_match)} · "
        f"부서 일치 {report.rate(report.dept_match)} · "
        f"RETURN 비불량(subtype 필요) {report.non_defect_returns}"
    )
    print(
        f"  priority_rule_id 일치 {report.rate(report.priority_rule_match)} · "
        f"우선순위 일치 {report.rate(report.priority_match)} · "
        f"다름: 상담원 조정 {report.priority_diff_adjusted} / "
        f"설명 안 됨 {report.priority_diff_unexplained}"
    )
    print(
        f"  required_info 일치 {report.rate(report.required_match)} · "
        f"차단 항목 일관 {report.rate(report.blocking_consistent)}"
    )
    for kind, ticket_ids in report.mismatches.items():
        print(f"  ! {kind} 불일치 {len(ticket_ids)}건 예: {', '.join(ticket_ids[:5])}")


def main() -> None:
    import pandas as pd  # 검수에만 쓴다 (data extra)

    if not RAW_TICKETS_PATH.is_file():
        sys.exit(f"Input workbook not found: {RAW_TICKETS_PATH}")
    tickets = pd.read_excel(RAW_TICKETS_PATH, sheet_name="tickets")
    tables = load_tables()
    for split in ("train", "valid", "test"):
        rows = tickets.loc[tickets["data_split"].eq(split)].to_dict("records")
        _print_report(split, audit_tickets(tables, rows))


if __name__ == "__main__":
    main()
