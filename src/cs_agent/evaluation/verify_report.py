# 자동 점검 통과율·재작성 횟수 보고 (CSA-31 완료 기준 · 담당 김동규)
# 실행 예: LLM_PROVIDER=live uv run --extra llm --extra data \
#            python -m cs_agent.evaluation.verify_report --split valid --limit 100
#
# valid 문의를 그래프(분석 → 검색 → 답변 → 자동 점검 ⑩ → 재작성)에 넣고, 답변 경로(draft)로 간
# 문의에서 다음을 낸다.
# - 첫 답변 점검 통과율, 최종 통과율(재작성 후), 보류(ON_HOLD) 비율
# - 재작성 횟수 분포 (0 / 1 / 2회, settings.max_verify_retries)
# - 점검별 실패 횟수와 실패 사유 예시 (모든 점검 호출 기준)
# 검색기는 default_retrievers() (DB 에 벡터가 없으면 키워드 검색). 결과 원본은 --json 에 남긴다.
# 답변 작성(⑨)·검색 품질이 바뀌면 숫자가 바뀐다. 점검 자체의 정확도는 tests/test_verification.py.
import argparse
import csv
import json
import threading
from collections import Counter
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any

from cs_agent.agents import verification
from cs_agent.config import get_settings
from cs_agent.domain import TicketStatus
from cs_agent.schemas import InquiryIn

WORKERS = 4


def _inquiry(row: dict[str, str]) -> InquiryIn:
    """tickets 행 → 접수 입력. 유형·제품은 넣지 않는다 (분석 ②③ 이 찾게)."""
    fields: dict[str, Any] = {
        "channel": row["channel"] or "email",
        "customer_id": row.get("customer_id") or None,
        "customer_tier": row.get("customer_tier") or "STANDARD",
        "country": row.get("country") or None,
        "language": row.get("language") or None,
        "subject": row.get("inquiry_subject", ""),
        "body": row["inquiry_body"],
    }
    if row.get("received_at_utc"):
        fields["received_at"] = datetime.fromisoformat(
            row["received_at_utc"].replace("Z", "+00:00")
        )
    return InquiryIn(**fields)


def run(rows: Sequence[dict[str, str]], workers: int = WORKERS) -> list[dict[str, Any]]:
    from cs_agent.agents.retrieval import default_retrievers
    from cs_agent.graph.builder import GraphDeps, build_ticket_graph
    from cs_agent.llm.router import get_router
    from cs_agent.services.tickets import TicketService

    docs, cases = default_retrievers()
    calls: dict[str, list[list[dict]]] = {}
    current = threading.local()
    lock = threading.Lock()

    def recording_verify(*args: Any, **kwargs: Any) -> Any:
        checks = verification.verify(*args, **kwargs)
        with lock:
            calls.setdefault(current.ticket, []).append([c.model_dump() for c in checks])
        return checks

    llm = get_router()
    local = threading.local()

    def service() -> TicketService:
        if not hasattr(local, "service"):
            deps = GraphDeps(llm=llm, docs=docs, cases=cases, verify=recording_verify)
            local.service = TicketService(build_ticket_graph(deps))
        return local.service

    def one(row: dict[str, str]) -> dict[str, Any]:
        current.ticket = row["ticket_id"]
        try:
            ticket = service().submit(_inquiry(row))
        except Exception as e:  # 한 건 실패로 전체를 멈추지 않는다
            return {"ticket": row["ticket_id"], "error": f"{type(e).__name__}: {e}"[:200]}
        state = service().graph.get_state(service()._config(ticket.ticket_id)).values
        return {
            "ticket": row["ticket_id"],
            "category": row["category_code"],
            "language": row["language"],
            "route": str(ticket.route) if ticket.route else None,
            "status": str(ticket.status),
            "retries": state.get("retries", 0),
            "checks": calls.get(row["ticket_id"], []),
            # 점검이 놓친 것이 없는지 사람이 표본을 읽어 보게 마지막 답변과 근거를 남긴다
            "draft": state["draft"].text if state.get("draft") else None,
            "evidence": [f"{e.doc_id}#{e.section or ''}" for e in state.get("evidence", [])],
            "reference": f"{row['reference_doc_id']}#{row['reference_section']}",
        }

    with ThreadPoolExecutor(workers) as pool:
        return list(pool.map(one, rows))


def report(results: Sequence[dict[str, Any]]) -> str:
    drafted = [r for r in results if r.get("checks")]
    errors = [r for r in results if "error" in r]
    lines = [
        f"문의 {len(results)}건 · 답변 경로(점검 1회 이상) {len(drafted)}건 · 오류 {len(errors)}건",
        f"경로: {dict(Counter(r.get('route') for r in results if 'error' not in r))}",
    ]
    if not drafted:
        return "\n".join(lines)
    first_pass = sum(all(c["passed"] for c in r["checks"][0]) for r in drafted)
    final_pass = sum(all(c["passed"] for c in r["checks"][-1]) for r in drafted)
    held = sum(r["status"] == TicketStatus.ON_HOLD for r in drafted)
    n = len(drafted)
    lines += [
        f"첫 답변 통과 {first_pass}/{n} ({first_pass / n:.1%}) · 재작성 후 최종 통과 "
        f"{final_pass}/{n} ({final_pass / n:.1%}) · 보류(ON_HOLD) {held}/{n} ({held / n:.1%})",
        "재작성 횟수: "
        + ", ".join(
            f"{k}회 {v}건"
            for k, v in sorted(Counter(len(r["checks"]) - 1 for r in drafted).items())
        ),
    ]
    failures: Counter[str] = Counter()
    examples: dict[str, list[str]] = {}
    total_calls = 0
    for r in drafted:
        for call in r["checks"]:
            total_calls += 1
            for c in call:
                if not c["passed"]:
                    failures[c["name"]] += 1
                    examples.setdefault(c["name"], [])
                    if len(examples[c["name"]]) < 3:
                        examples[c["name"]].append(
                            f"{r['ticket']} ({r['language']}): {c['reason'][:140]}"
                        )
    lines.append(f"점검 호출 {total_calls}회 중 실패: {dict(failures.most_common())}")
    by_category = Counter(r["category"] for r in drafted)
    passed_by_category = Counter(
        r["category"] for r in drafted if all(c["passed"] for c in r["checks"][0])
    )
    lines.append(
        "유형별 첫 답변 통과: "
        + ", ".join(f"{k} {passed_by_category[k]}/{v}" for k, v in sorted(by_category.items()))
    )
    for name, items in examples.items():
        lines.append(f"\n[{name}] 예시")
        lines += [f"  - {x}" for x in items]
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="자동 점검 통과율·재작성 횟수 보고")
    parser.add_argument("--split", default="valid", choices=("train", "valid", "test"))
    parser.add_argument("--limit", type=int, default=0, help="앞에서부터 N건만 (0 이면 전체)")
    parser.add_argument("--workers", type=int, default=WORKERS)
    parser.add_argument("--json", type=Path, help="결과 원본 저장 경로")
    args = parser.parse_args(argv)

    with (get_settings().raw_data_dir / "tickets.csv").open(encoding="utf-8-sig") as f:
        rows = [r for r in csv.DictReader(f) if r["data_split"] == args.split]
    if args.limit:
        rows = rows[: args.limit]
    results = run(rows, args.workers)
    print(report(results))
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(results, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
