"""기준표 로더 (CSA-19 기준표 정리 · 담당 박종석).

`data/ref/` 아래 CSV를 읽는다. 지금 들어 있는 routing_rules·required_info·priority_rules는
tickets 4,000건에서 역산한 임시본이고, sla_policy는 복원본이다. 원본 ref/ 파일을 받으면
같은 열 이름으로 교체한다 (N-02: 규칙은 코드가 아니라 파일에).
"""

import csv
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from cs_agent.config import get_settings


def _read(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _split(value: str) -> list[str]:
    return [v for v in value.split(";") if v]


@dataclass(frozen=True)
class Product:
    code: str
    name: str
    family: str
    division: str


@dataclass(frozen=True)
class RefTables:
    products: dict[str, Product]
    routing: dict[tuple[str, str], tuple[str, str]]  # (family, category) -> (rule_id, dept)
    required: dict[tuple[str, str], tuple[list[str], list[str]]]  # -> (required, blocking)
    priority: list[dict[str, str]]
    sla: dict[tuple[str, str, str], dict[str, str]]  # (category, tier, priority) -> row
    navigation: dict[str, dict[str, str]]  # intent -> row (CSA-33)


@lru_cache
def load_tables(ref_dir: Path | None = None) -> RefTables:
    ref = ref_dir or get_settings().ref_dir
    products = {
        r["product_code"]: Product(
            r["product_code"], r["product_name"], r["product_family"], r["division"]
        )
        for r in _read(ref / "product_master.csv")
    }
    routing = {
        (r["product_family"], r["category"]): (r["routing_rule_id"], r["assigned_dept"])
        for r in _read(ref / "routing_rules.csv")
    }
    required = {
        (r["product_family"], r["category"]): (
            _split(r["required_info"]),
            _split(r["blocking_info"]),
        )
        for r in _read(ref / "required_info.csv")
    }
    sla = {
        (r["category"], r["customer_tier"], r["priority"]): r for r in _read(ref / "sla_policy.csv")
    }
    navigation = {r["intent"]: r for r in _read(ref / "navigation_rules.csv")}
    return RefTables(
        products=products,
        routing=routing,
        required=required,
        priority=_read(ref / "priority_rules.csv"),
        sla=sla,
        navigation=navigation,
    )
