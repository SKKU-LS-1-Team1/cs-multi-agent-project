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
# 할 일
# 1. load_tables(): 위 CSV를 읽어 RefTables 로 돌려준다. 한 번만 읽도록 캐시(lru_cache).
# 2. routing 은 rule_source 우선순위대로 찾게 만든다. RETURN 이 불량이 아니면 SUBTYPE_OVERRIDE.
# 3. tickets 와 대조해 검수: routing_rule_id·priority_rule_id·required_info 열 일치율을 낸다.
#    priority 가 규칙과 다른 건은 상담원 조정(priority_adjusted_by_agent)인지 확인.
# 4. 제품 트리(api/products.py)의 대분류는 원본에 없다. family 를 묶는 대분류 표를 정해서 둔다.
#
# 완료 기준: 김동규 님 규칙 처리(CSA-22)가 이 표만으로 valid 부서·우선순위 일치율을 낼 수 있음
#
# 할 일 1·2 는 CSA-22 규칙 처리를 돌리려고 김동규가 먼저 채웠다. 할 일 3·4 는 CSA-19.
# 규칙 판단은 rules/engine.py 한 곳에서 한다. 검수(할 일 3)도 engine.apply_rules 를 불러 잰다.
# 검수 실행: uv run python -m cs_agent.rules.tables
import csv
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import TypeVar

ALL = "ALL"  # routing_rules.csv 에서 제품군 구분 없는 규칙
RULE_SOURCE_ORDER = ("SUBTYPE_OVERRIDE", "FAMILY_OVERRIDE", "CATEGORY_DEFAULT")

K = TypeVar("K")
V = TypeVar("V")


@dataclass(frozen=True)
class Product:
    code: str
    name: str
    family: str
    division: str = ""  # family_divisions.csv (원본에 없음, 할 일 4)
    # 기준표 원문을 보존한다. 금액·수량 계산 시 사용하는 쪽에서 Decimal 등으로 검증한다.
    list_price_usd: str = ""
    std_lead_time_weeks: str = ""
    moq: str = ""
    standards: str = ""
    certifications: str = ""
    doc_ids: tuple[str, ...] = ()


# eq=False: dict 필드가 있어 값 비교 해시는 못 만든다. 같은 객체인지로 비교·해시해서
# lru_cache 인자나 set 에 넣을 수 있게 한다 (load_tables 는 같은 경로면 같은 객체를 준다).
@dataclass(frozen=True, eq=False)
class RefTables:
    products: dict[str, Product]
    # (family, category) -> 행. SUBTYPE_OVERRIDE 는 ("ALL", category) 로 들어간다.
    routing: dict[tuple[str, str], dict[str, str]]
    required: dict[tuple[str, str], tuple[list[str], list[str]]]  # -> (required, blocking)
    priority: list[dict[str, str]]  # order 순
    sla: dict[tuple[str, str, str], dict[str, str]]  # (category, tier, priority) -> row
    navigation: dict[str, dict[str, str]]  # intent -> row (CSA-33)
    escalation: list[dict[str, str]] = field(default_factory=list)  # rule_source=ESCALATION 행
    divisions: dict[str, str] = field(default_factory=dict)  # division -> 표시 이름
    family_divisions: dict[str, str] = field(default_factory=dict)  # family -> division
    field_labels: dict[str, str] = field(default_factory=dict)  # info_field_codebook
    urgency: dict[str, str] = field(default_factory=dict)  # urgency -> 설명
    departments: dict[str, dict[str, str]] = field(default_factory=dict)  # dept_code -> row
    customers: dict[str, dict[str, str]] = field(default_factory=dict)  # customer_id -> row
    spec_facts: dict[str, list[dict[str, str]]] = field(default_factory=dict)  # product_code ->
    faults: list[dict[str, str]] = field(default_factory=list)
    firmware: dict[str, list[dict[str, str]]] = field(default_factory=dict)  # product_code ->


def _read(path: Path) -> list[dict[str, str]]:
    """CSV → 행 목록. 열 개수가 머리글과 다른 줄은 파일 이름·줄 번호와 함께 멈춘다."""
    if not path.exists():
        return []
    rows: list[dict[str, str]] = []
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # 열이 많으면 남는 값이 None 키에, 적으면 빠진 열 값이 None 으로 들어온다
            if None in row or None in row.values():
                columns = len(reader.fieldnames or [])
                raise ValueError(
                    f"{path.name}:{reader.line_num}: 열 개수가 머리글({columns}개)과 다르다."
                    " 값에 쉼표가 있으면 큰따옴표로 감싼다"
                )
            rows.append(row)
    return rows


def _split(value: str) -> list[str]:
    return [v.strip() for v in value.split(";") if v.strip()]


def _unique(items: Iterable[tuple[K, V]], name: str) -> dict[K, V]:
    """(키, 값) → dict. 같은 키가 두 번 나오면 마지막 줄로 덮어쓰지 않고 멈춘다."""
    out: dict[K, V] = {}
    for key, value in items:
        if key in out:
            raise ValueError(f"{name}: 키 {key} 가 두 번 있다")
        out[key] = value
    return out


def _group(rows: list[dict[str, str]], key: str) -> dict[str, list[dict[str, str]]]:
    grouped: dict[str, list[dict[str, str]]] = {}
    for r in rows:
        grouped.setdefault(r[key], []).append(r)
    return grouped


@lru_cache
def _load(ref_dir: Path) -> RefTables:
    division_rows = _read(ref_dir / "family_divisions.csv")
    family_divisions = _unique(
        ((r["family"], r["division"]) for r in division_rows), "family_divisions.csv"
    )
    # 대분류 하나가 여러 제품군 줄에 나오므로 중복은 허용하되 표시 이름은 같아야 한다
    divisions: dict[str, str] = {}
    for r in division_rows:
        label = divisions.setdefault(r["division"], r["division_label"])
        if label != r["division_label"]:
            raise ValueError(
                f"family_divisions.csv: 대분류 {r['division']} 의 표시 이름이"
                f" {label} / {r['division_label']} 로 다르다"
            )

    products = _unique(
        (
            (
                r["product_code"],
                Product(
                    r["product_code"],
                    r["product_name"],
                    r["family"],
                    family_divisions.get(r["family"], ""),
                    list_price_usd=r.get("list_price_usd", "").strip(),
                    std_lead_time_weeks=r.get("std_lead_time_weeks", "").strip(),
                    moq=r.get("moq", "").strip(),
                    standards=r.get("standards", "").strip(),
                    certifications=r.get("certifications", "").strip(),
                    doc_ids=tuple(_split(r.get("doc_ids", ""))),
                ),
            )
            for r in _read(ref_dir / "product_master.csv")
        ),
        "product_master.csv",
    )

    routing: dict[tuple[str, str], dict[str, str]] = {}
    escalation: list[dict[str, str]] = []
    rows = _read(ref_dir / "routing_rules.csv")
    for r in rows:
        if r["rule_source"] == "ESCALATION":
            escalation.append(r)
    # 같은 키가 겹치면 우선순위 높은 rule_source 가 남도록 낮은 것부터 넣는다.
    # 같은 rule_source 안에서 키가 겹치는 것은 표 오류다.
    for source in reversed(RULE_SOURCE_ORDER):
        same_source = _unique(
            (((r["family"], r["category"]), r) for r in rows if r["rule_source"] == source),
            f"routing_rules.csv ({source})",
        )
        routing.update(same_source)

    required = _unique(
        (
            (
                (r["family"], r["category"]),
                (_split(r["required_fields"]), _split(r["blocking_fields"])),
            )
            for r in _read(ref_dir / "required_info.csv")
        ),
        "required_info.csv",
    )
    priority_rows = _read(ref_dir / "priority_rules.csv")
    _unique(((r["order"], r) for r in priority_rows), "priority_rules.csv (order)")
    priority = sorted(priority_rows, key=lambda r: int(r["order"]))
    sla = _unique(
        (
            ((r["category"], r["customer_tier"], r["priority"]), r)
            for r in _read(ref_dir / "sla_policy.csv")
        ),
        "sla_policy.csv",
    )
    navigation = _unique(
        ((r["intent"], r) for r in _read(ref_dir / "navigation_rules.csv")),
        "navigation_rules.csv",
    )
    return RefTables(
        products,
        routing,
        required,
        priority,
        sla,
        navigation,
        escalation,
        divisions=divisions,
        family_divisions=family_divisions,
        field_labels=_unique(
            ((r["field"], r["label"]) for r in _read(ref_dir / "info_field_codebook.csv")),
            "info_field_codebook.csv",
        ),
        urgency=_unique(
            ((r["urgency"], r["description"]) for r in _read(ref_dir / "urgency_codebook.csv")),
            "urgency_codebook.csv",
        ),
        departments=_unique(
            ((r["dept_code"], r) for r in _read(ref_dir / "departments.csv")), "departments.csv"
        ),
        customers=_unique(
            ((r["customer_id"], r) for r in _read(ref_dir / "customers.csv")), "customers.csv"
        ),
        spec_facts=_group(_read(ref_dir / "product_spec_facts.csv"), "product_code"),
        faults=_read(ref_dir / "fault_catalog.csv"),
        firmware=_group(_read(ref_dir / "firmware_history.csv"), "product_code"),
    )


def load_tables(ref_dir: Path | None = None) -> RefTables:
    """data/ref/*.csv → RefTables. 경로 기본값은 config.Settings.ref_dir."""
    if ref_dir is None:
        from cs_agent.config import get_settings

        ref_dir = get_settings().ref_dir
    return _load(Path(ref_dir))


# 검수 (할 일 3) — tickets 정답 열로 추출 결과를 만들어 engine.apply_rules 결과와 대조한다.
# 추출 정확도는 CSA-26 에서 따로 잰다.

NON_DEFECT_RETURN = "RT-ALL-RETURN-NON_DEFECT"


@dataclass
class AuditReport:
    total: int = 0
    routing_match: int = 0
    dept_match: int = 0
    non_defect_returns: int = 0  # 추출이 return_defect=False 를 넘겨야 맞는 건
    priority_rule_match: int = 0
    priority_match: int = 0
    priority_diff_adjusted: int = 0  # 규칙과 다르지만 상담원 조정(Y)인 건
    priority_diff_unexplained: int = 0
    required_match: int = 0
    missing_match: int = 0
    missing_blocking_match: int = 0
    mismatches: dict[str, list[str]] = field(default_factory=dict)

    def note(self, kind: str, ticket_id: str) -> None:
        self.mismatches.setdefault(kind, []).append(ticket_id)

    def rate(self, count: int) -> str:
        return f"{count}/{self.total} ({count / self.total:.1%})" if self.total else "0/0"


def audit_tickets(
    tickets: Iterable[Mapping[str, str]], tables: RefTables | None = None
) -> AuditReport:
    # engine 이 이 모듈을 import 하므로 여기서 불러온다
    from cs_agent.domain import Category, Urgency
    from cs_agent.rules.engine import apply_rules
    from cs_agent.schemas import Classification, Extraction

    tables = tables or load_tables()
    report = AuditReport()
    for row in tickets:
        report.total += 1
        ticket_id = row["ticket_id"]
        category = Category(row["category_code"])
        return_defect = None
        if category == Category.RETURN:
            return_defect = row["routing_rule_id"] != NON_DEFECT_RETURN
            report.non_defect_returns += not return_defect
        extraction = Extraction(
            product_code=row["product_code"] or None,
            product_family=row["product_family"] or None,
            urgency=Urgency(row["urgency_flag"] or Urgency.NONE),
            provided_info=_split(row["provided_info"]),
            return_defect=return_defect,
        )
        result = apply_rules(
            Classification(category=category), extraction, row["customer_tier"], tables
        )

        checks = {
            "routing": result.routing_rule_id == row["routing_rule_id"],
            "dept": result.assigned_dept == row["assigned_dept"],
            "priority_rule": result.priority_rule_id == row["priority_rule_id"],
            "required_info": set(result.required_info) == set(_split(row["required_info"])),
            "missing_info": set(result.missing_info) == set(_split(row["missing_info"])),
            "missing_blocking": set(result.missing_blocking)
            == set(_split(row["missing_blocking_info"])),
        }
        report.routing_match += checks["routing"]
        report.dept_match += checks["dept"]
        report.priority_rule_match += checks["priority_rule"]
        report.required_match += checks["required_info"]
        report.missing_match += checks["missing_info"]
        report.missing_blocking_match += checks["missing_blocking"]
        for kind, ok in checks.items():
            if not ok:
                report.note(kind, ticket_id)

        if result.priority == row["priority"]:
            report.priority_match += 1
        elif row["priority_adjusted_by_agent"] == "Y":
            report.priority_diff_adjusted += 1
        else:
            report.priority_diff_unexplained += 1
            report.note("priority", ticket_id)
    return report


def _print_report(split: str, report: AuditReport) -> None:
    print(f"[{split}] tickets={report.total}")
    print(
        f"  routing_rule_id 일치 {report.rate(report.routing_match)} · "
        f"부서 일치 {report.rate(report.dept_match)} · "
        f"RETURN 비불량(return_defect=False) {report.non_defect_returns}"
    )
    print(
        f"  priority_rule_id 일치 {report.rate(report.priority_rule_match)} · "
        f"우선순위 일치 {report.rate(report.priority_match)} · "
        f"다름: 상담원 조정 {report.priority_diff_adjusted} / "
        f"설명 안 됨 {report.priority_diff_unexplained}"
    )
    print(
        f"  required_info 일치 {report.rate(report.required_match)} · "
        f"누락 항목 일치 {report.rate(report.missing_match)} · "
        f"차단성 누락 일치 {report.rate(report.missing_blocking_match)}"
    )
    for kind, ticket_ids in report.mismatches.items():
        print(f"  ! {kind} 불일치 {len(ticket_ids)}건 예: {', '.join(ticket_ids[:5])}")


def main() -> None:
    from cs_agent.config import get_settings

    path = get_settings().raw_data_dir / "tickets.csv"
    tickets = _read(path)
    if not tickets:
        raise SystemExit(f"tickets not found: {path}")
    tables = load_tables()
    for split in ("train", "valid", "test"):
        rows = [r for r in tickets if r["data_split"] == split]
        _print_report(split, audit_tickets(rows, tables))


if __name__ == "__main__":
    main()
