"""시험 문의 597건 평가 스크립트 (CSA-50 · 담당 박종석) → 결과 정리 (CSA-51).

test 분할은 마지막에 한 번만 돌린다. 개발 중에는 `--split valid` (603건).
실행: `uv run --extra data python -m cs_agent.evaluation.run_eval --split valid`
"""

import argparse
import json
import time

from cs_agent.config import get_settings
from cs_agent.evaluation.metrics import accuracy, p95, recall
from cs_agent.schemas import InquiryIn
from cs_agent.services.tickets import TicketService


def main() -> None:
    import pandas as pd  # extra: data

    parser = argparse.ArgumentParser()
    parser.add_argument("--split", default="valid", choices=["valid", "test"])
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    path = get_settings().raw_data_dir.parent / "processed" / f"tickets_{args.split}.parquet"
    gold = pd.read_parquet(path)
    if args.limit:
        gold = gold.head(args.limit)

    svc = TicketService()
    rows = []
    for _, g in gold.iterrows():
        started = time.perf_counter()
        out = svc.submit(
            InquiryIn(
                channel=g["channel"],
                customer_tier=g["customer_tier"],
                language=g["language"],
                subject=g["inquiry_subject"] or "",
                body=g["inquiry_body"],
            )
        )
        rows.append({"gold": g, "out": out, "latency": time.perf_counter() - started})

    def _missing(value) -> set:
        return set(value.split(";")) if isinstance(value, str) and value else set()

    report = {
        "split": args.split,
        "n": len(rows),
        "category_acc": accuracy([r["out"].category for r in rows], list(gold["category_code"])),
        "dept_acc": accuracy([r["out"].assigned_dept for r in rows], list(gold["assigned_dept"])),
        "priority_acc": accuracy([r["out"].priority for r in rows], list(gold["priority"])),
        "latency_p95_s": p95([r["latency"] for r in rows]),
        # TODO(CSA-50): K2 무수정 승인 가능률, K3 근거 일치율(reference_doc_id + section)
        "missing_recall": recall(
            [set()] * len(rows),  # TODO(CSA-50): TicketOut에 missing_info 노출 후 연결
            [_missing(v) for v in gold["missing_info"]],
        ),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
