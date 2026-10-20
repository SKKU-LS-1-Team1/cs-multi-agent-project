# SQL 파일 불러 쓰기 (CSA-20 · 담당 박종석)
#
# db/sql/*.sql 은 "-- name: 이름" 줄로 쿼리를 나눠 둔다. 이름으로 꺼내 SQLAlchemy text 로 실행한다.
#   rows = run(conn, "work_list", "work_list", dept="TS_LV")        # → list[dict]
#   rows = run(conn, "dept_dashboard", "dept_status")               # 빠진 파라미터는 NULL
# 쓰는 곳: 작업 목록(CSA-40), 부서 대시보드(CSA-43), 평가(CSA-50 — load_tickets_gold 먼저).
import csv
import json
import re
from collections.abc import Iterable
from functools import lru_cache
from pathlib import Path
from typing import Any

import sqlalchemy as sa

SQL_DIR = Path(__file__).parent / "sql"
_NAME = re.compile(r"^--\s*name:\s*(\w+)\s*$", re.M)
GOLD_SPLITS = ("valid", "test")


@lru_cache
def load_queries(file: str) -> dict[str, str]:
    """db/sql/{file}.sql → {이름: SQL}. 이름 줄 앞의 머리 주석은 버린다."""
    text = (SQL_DIR / f"{file}.sql").read_text(encoding="utf-8")
    parts = _NAME.split(text)
    queries: dict[str, str] = {}
    for name, body in zip(parts[1::2], parts[2::2], strict=True):
        if name in queries:
            raise ValueError(f"{file}.sql: 쿼리 이름이 겹칩니다: {name}")
        queries[name] = body.strip().rstrip(";").strip()
    return queries


def query(file: str, name: str) -> sa.TextClause:
    try:
        return sa.text(load_queries(file)[name])
    except KeyError:
        raise KeyError(f"{file}.sql 에 '{name}' 쿼리가 없습니다") from None


def params_of(file: str, name: str) -> set[str]:
    """쿼리가 받는 파라미터 이름 (SQLAlchemy 가 :이름 으로 인식한 것)."""
    return set(query(file, name).compile().params)


def run(conn: Any, file: str, name: str, **params: Any) -> list[dict[str, Any]]:
    """쿼리를 실행해 행을 dict 로 돌려준다. 넘기지 않은 파라미터는 NULL(=기본값)."""
    unknown = set(params) - params_of(file, name)
    if unknown:
        raise TypeError(f"{file}.{name} 에 없는 파라미터: {sorted(unknown)}")
    values = dict.fromkeys(params_of(file, name)) | params
    result = conn.execute(query(file, name), values)
    return [dict(row) for row in result.mappings()] if result.returns_rows else []


def _split(value: str) -> str:
    return json.dumps([v.strip() for v in value.split(";") if v.strip()])


def gold_rows(tickets: Iterable[dict[str, str]], splits: Iterable[str] = GOLD_SPLITS) -> list[dict]:
    """tickets.csv 행 → eval.tickets_gold 행 (valid·test 만)."""
    splits = set(splits)
    rows = []
    for t in tickets:
        if t["data_split"] not in splits:
            continue
        rows.append(
            {
                "ticket_id": t["ticket_id"],
                "data_split": t["data_split"],
                "language": t["language"] or None,
                "body_language": t["body_language"] or None,
                "customer_tier": t["customer_tier"] or None,
                "product_code": t["product_code"] or None,
                "category": t["category_code"],
                "urgency_flag": t["urgency_flag"] or None,
                "priority": t["priority"] or None,
                "priority_rule_id": t["priority_rule_id"] or None,
                "priority_adjusted_by_agent": t["priority_adjusted_by_agent"] == "Y",
                "assigned_dept": t["assigned_dept"] or None,
                "routing_rule_id": t["routing_rule_id"] or None,
                "required_info": _split(t["required_info"]),
                "missing_info": _split(t["missing_info"]),
                "missing_blocking_info": _split(t["missing_blocking_info"]),
                "info_request_sent": t["info_request_sent"] == "Y",
                "reference_doc_id": t["reference_doc_id"] or None,
                "reference_section": t["reference_section"] or None,
            }
        )
    return rows


def load_tickets_gold(
    conn: Any, tickets_csv: Path | None = None, splits: Iterable[str] = GOLD_SPLITS
) -> int:
    """eval 스키마·정답 테이블·결과 뷰를 만들고 정답을 넣는다 (다시 돌려도 됨). → 넣은 건수."""
    if tickets_csv is None:
        from cs_agent.config import get_settings

        tickets_csv = get_settings().raw_data_dir / "tickets.csv"
    with tickets_csv.open(encoding="utf-8-sig", newline="") as f:
        rows = gold_rows(csv.DictReader(f), splits)
    for name in ("create_eval_schema", "create_tickets_gold", "create_ticket_results"):
        conn.execute(query("eval_join", name))
    if rows:
        conn.execute(query("eval_join", "upsert_tickets_gold"), rows)
    return len(rows)
