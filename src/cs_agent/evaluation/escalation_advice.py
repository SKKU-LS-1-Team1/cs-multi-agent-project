# 이관 권장 측정. 정답은 tickets.csv 의 escalated (합성 데이터, 미결·안전 건 제외).
#   uv run --all-extras python -m cs_agent.evaluation.escalation_advice --split valid
# 추출값은 원천 값을 쓴다 (분류·추출 오류는 포함되지 않는다). LLM_PROVIDER=live 필요.
import argparse
import csv
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

from cs_agent.agents.escalation_advice import safe_assess
from cs_agent.config import get_settings
from cs_agent.domain import Category
from cs_agent.llm.router import get_router
from cs_agent.rules.tables import load_tables

UNDECIDED = {"IN_PROGRESS", "NEW", "WAITING_CUSTOMER"}


def rows_of(split: str, limit: int | None = None) -> list[dict]:
    path = get_settings().raw_data_dir / "tickets.csv"
    with path.open(encoding="utf-8-sig", newline="") as f:
        rows = [
            r
            for r in csv.DictReader(f)
            if r["data_split"] == split
            and r["status"] not in UNDECIDED
            and r["urgency_flag"] != "SAFETY"
        ]
    return rows[:limit]


def state_of(row: dict, tables) -> dict:
    routes = [*tables.routing.values(), *tables.escalation]
    route = next((r for r in routes if r["rule_id"] == row["routing_rule_id"]), {})
    return {
        "inquiry": SimpleNamespace(subject=row["inquiry_subject"], body=row["inquiry_body"]),
        "classification": SimpleNamespace(category=Category(row["category_code"])),
        "extraction": SimpleNamespace(
            product_code=row["product_code"],
            error_code=row["error_code_reported"],
            return_defect=None,
        ),
        "rules": SimpleNamespace(
            routing_rule_id=row["routing_rule_id"],
            priority=row["priority"],
            escalate_to=route.get("escalation_dept") or None,
        ),
    }


def summarize(pairs: list[tuple[bool, bool]]) -> dict:
    """(실제 이관, 권장) 쌍 → 권장 비율·정밀도·재현율."""
    total = len(pairs)
    actual = sum(y for y, _ in pairs)
    advised = sum(p for _, p in pairs)
    hits = sum(y and p for y, p in pairs)
    return {
        "n": total,
        "actual_rate": round(actual / total, 3) if total else 0.0,
        "advised_rate": round(advised / total, 3) if total else 0.0,
        "precision": round(hits / advised, 3) if advised else 0.0,
        "recall": round(hits / actual, 3) if actual else 0.0,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", default="valid", choices=["train", "valid", "test"])
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    tables, llm = load_tables(), get_router()
    rows = rows_of(args.split, args.limit)

    def one(row: dict) -> tuple[bool, bool]:
        advice = safe_assess(state_of(row, tables), tables, llm)
        return row["escalated"] == "Y", bool(advice and advice["decision"] == "recommended")

    with ThreadPoolExecutor(8) as pool:
        print(summarize(list(pool.map(one, rows))))


if __name__ == "__main__":
    main()
