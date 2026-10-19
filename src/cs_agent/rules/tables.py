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
# 지금 들어간 것 (CSA-22 규칙 처리를 돌리려고 김동규가 먼저 채움): 할 일 1·2.
# TODO(CSA-19): 할 일 3 검수, 할 일 4 대분류 표 (Product.division 은 아직 빈 값).
import csv
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

ALL = "ALL"  # routing_rules.csv 에서 제품군 구분 없는 규칙
RULE_SOURCE_ORDER = ("SUBTYPE_OVERRIDE", "FAMILY_OVERRIDE", "CATEGORY_DEFAULT")


@dataclass(frozen=True)
class Product:
    code: str
    name: str
    family: str
    division: str = ""  # 원본에 없음, 할 일 4


@dataclass(frozen=True)
class RefTables:
    products: dict[str, Product]
    # (family, category) -> 행. SUBTYPE_OVERRIDE 는 ("ALL", category) 로 들어간다.
    routing: dict[tuple[str, str], dict[str, str]]
    required: dict[tuple[str, str], tuple[list[str], list[str]]]  # -> (required, blocking)
    priority: list[dict[str, str]]  # order 순
    sla: dict[tuple[str, str, str], dict[str, str]]  # (category, tier, priority) -> row
    navigation: dict[str, dict[str, str]]  # intent -> row (CSA-33)
    escalation: list[dict[str, str]] = field(default_factory=list)  # rule_source=ESCALATION 행


def _read(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _split(value: str) -> list[str]:
    return [v.strip() for v in value.split(";") if v.strip()]


@lru_cache
def _load(ref_dir: Path) -> RefTables:
    products = {
        r["product_code"]: Product(r["product_code"], r["product_name"], r["family"])
        for r in _read(ref_dir / "product_master.csv")
    }

    routing: dict[tuple[str, str], dict[str, str]] = {}
    escalation: list[dict[str, str]] = []
    rows = _read(ref_dir / "routing_rules.csv")
    for r in rows:
        if r["rule_source"] == "ESCALATION":
            escalation.append(r)
    # 같은 키가 겹치면 우선순위 높은 rule_source 가 남도록 낮은 것부터 넣는다
    for source in reversed(RULE_SOURCE_ORDER):
        for r in rows:
            if r["rule_source"] == source:
                routing[(r["family"], r["category"])] = r

    required = {
        (r["family"], r["category"]): (_split(r["required_fields"]), _split(r["blocking_fields"]))
        for r in _read(ref_dir / "required_info.csv")
    }
    priority = sorted(_read(ref_dir / "priority_rules.csv"), key=lambda r: int(r["order"]))
    sla = {
        (r["category"], r["customer_tier"], r["priority"]): r
        for r in _read(ref_dir / "sla_policy.csv")
    }
    navigation = {r["intent"]: r for r in _read(ref_dir / "navigation_rules.csv")}
    return RefTables(products, routing, required, priority, sla, navigation, escalation)


def load_tables(ref_dir: Path | None = None) -> RefTables:
    """data/ref/*.csv → RefTables. 경로 기본값은 config.Settings.ref_dir."""
    if ref_dir is None:
        from cs_agent.config import get_settings

        ref_dir = get_settings().ref_dir
    return _load(Path(ref_dir))
