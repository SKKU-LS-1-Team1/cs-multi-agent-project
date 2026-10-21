# 시험 문의 평가 스크립트 (CSA-50 · 담당 박종석) → 최종 결과 정리 (CSA-51)
# 실행 예: uv run --all-extras python -m cs_agent.evaluation.run_eval --split valid
#   (앱과 같이 모든 extra 가 필요하다 — obs(langfuse)가 없으면 LLM 호출 전에 실패해 전부 분석 대기)
#   빠른 확인: --limit 10, 시연: --demo, test 분할: --split test --final
#
# test 597건은 마지막에 한 번만 돌린다 (N-05). 개발 중에는 --split valid (603건).
#
# 할 일
# 1. data/processed/tickets_{split}.parquet 를 읽어 문의마다 TicketService.submit() 실행, 지연
#      시간 기록.
# 2. 정답과 비교: 유형(category_code), 부서(assigned_dept), 우선순위(priority), 누락
#      항목(missing_info),
#    근거(reference_doc_id, reference_section), 추가정보 요청 여부(info_request_sent).
# 3. evaluation/metrics.py 로 K1~K5 계산, JSON + 표로 저장
#      (data/processed/eval_{split}_{날짜}.json).
# 4. 유형별·언어별로 쪼개 본다. 틀린 건 목록을 따로 남겨 담당자에게 넘긴다.
# 5. 시연(CSA-15): test 를 순서대로 처리하며 해결 건을 사례 DB 에 쌓고, 앞 절반 vs 뒤 절반 비교.
#
# 정해 둔 것
# - 서비스는 앱(main.py)과 같이 만든다: PostgreSQL 기록(SqlRecords) + PostgresSaver + 설정의 LLM·
#   검색기. 정답 비교가 DB 의 ticket_results 임시 뷰(db/sql/eval_join.sql, CSA-20)라 DB 가 필요하다
#   (DB 가 없거나 스키마가 최신이 아니면 멈춘다). LLM_PROVIDER=live 여야 실제 성능이다.
# - 입력은 고객이 실제로 보내는 값만: 채널·고객·등급·국가·언어·제목·본문 (pipeline/mock_data.py 와
#   같다). 제품 코드·유형 같은 정답 열은 넣지 않는다. 접수 시각은 지금.
# - 정답 연결: InquiryIn.thread_ref = "{run_id}:{원본 ticket_id}" (eval_join.sql 규칙). 같은 원본을
#   여러 번 돌려도 실행마다 새 티켓이고, 결과는 이번 실행 티켓만 본다.
# - 틀린 건 목록은 처리 흐름에서 틀린 단계마다 담당 카드를 붙인다 (docs/JIRA_MAP.md):
#   유형 → CSA-26, 부서·우선순위 → CSA-22 (유형이 틀렸으면 그 탓이라 CSA-26),
#   누락 항목·추가정보 요청 여부 → CSA-26 (고객이 준 정보 추출), 근거 → CSA-28.
# - 저장: data/processed/eval_{split}_{YYYYMMDD}.json (전체 결과) + 같은 이름 .md (표).
#   같은 날 다시 돌리면 덮어쓴다.
# - --demo (할 일 5, CSA-15 시연 방식): 상담원 대신 실제 회신(tickets.final_reply)을 정답으로 쓴다.
#   답변 초안은 실제 회신으로 수정 승인(edit_approve) → 해결 확정해서 사례(live)가 사람의 답으로
#   쌓인다. 실제 회신이 없는 건·추가정보 요청문은 그대로 승인한다. AI 초안을 그대로 승인하면 사례가
#   AI 자신의 초안으로 쌓여 피드백 루프가 아니게 된다 (PR #31 리뷰).
#   "같은 내용이면 approve" 는 판정 기준이 없어 하지 않는다 → 시연의 K2 는 재지 않는다 (None).
#   앞 절반 vs 뒤 절반의 KPI 와 "live 사례를 근거로 쓴 문의 비율"을 비교한다.
import argparse
import json
import time
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import ExitStack, contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cs_agent.config import REPO_ROOT, get_settings
from cs_agent.domain import ReviewAction, TicketStatus
from cs_agent.evaluation.metrics import by_group, kpi_report, markdown_table
from cs_agent.schemas import InquiryIn, ReviewIn

PROCESSED_DIR = REPO_ROOT / "data" / "processed"
SPLITS = ("valid", "test", "train")
REPORT_COLUMNS = (
    "group",
    "processed",
    "category_accuracy",
    "K3_evidence_top3",
    "K4_dept_accuracy",
    "K4_priority_rule_accuracy",
    "K5_missing_recall",
    "K1_latency_p95_s",
)
DEMO_REVIEWER = "eval-demo"


# --- 입력 -----------------------------------------------------------------------------------


def _text(value: Any) -> str | None:
    if value is None or (isinstance(value, float) and value != value):  # NaN
        return None
    text = str(value).strip()
    return text or None


def build_inquiry(row: Mapping[str, Any], run_id: str) -> InquiryIn:
    """정답 열은 빼고 고객이 보내는 값만으로 문의를 만든다."""
    return InquiryIn(
        channel=_text(row.get("channel")) or "EMAIL",
        customer_id=_text(row.get("customer_id")),
        customer_tier=_text(row.get("customer_tier")) or "STANDARD",
        country=_text(row.get("country")),
        language=_text(row.get("language")),
        subject=_text(row.get("inquiry_subject")) or "",
        body=_text(row.get("inquiry_body")) or "",
        thread_ref=f"{run_id}:{row['ticket_id']}",
    )


def load_split(split: str, processed_dir: Path = PROCESSED_DIR) -> list[dict[str, Any]]:
    import pandas as pd  # extra: data

    path = processed_dir / f"tickets_{split}.parquet"
    if not path.is_file():
        raise SystemExit(
            f"{path} 가 없습니다: uv run --extra data python -m cs_agent.pipeline.prepare_data"
        )
    return pd.read_parquet(path).to_dict("records")


# --- 실행 -----------------------------------------------------------------------------------


@contextmanager
def open_service() -> Iterator[tuple[Any, Any]]:
    """앱과 같은 구성의 TicketService 와 DB 엔진. DB 가 없으면 여기서 멈춘다."""
    from cs_agent.cache.store import MemoryKV
    from cs_agent.db.session import get_engine
    from cs_agent.graph.builder import GraphDeps, build_ticket_graph, postgres_checkpointer
    from cs_agent.llm.router import get_router
    from cs_agent.main import _connect_db, _retrievers
    from cs_agent.rules.tables import load_tables
    from cs_agent.services.records import SqlRecords
    from cs_agent.services.tickets import TicketService

    settings = get_settings()
    sessionmaker = _connect_db(settings)
    embed_fn = None
    if settings.llm_provider == "live":
        from cs_agent.pipeline.embed_docs import embed as embed_fn
    llm = get_router()
    if llm.enabled:
        llm.kv = MemoryKV()
    docs, cases = _retrievers()
    deps = GraphDeps(llm=llm, tables=load_tables(), docs=docs, cases=cases)
    with ExitStack() as stack:
        checkpointer = stack.enter_context(postgres_checkpointer(settings.database_url))
        service = TicketService(
            build_ticket_graph(deps, checkpointer), SqlRecords(sessionmaker, embed_fn=embed_fn)
        )
        yield service, get_engine()


def submit_all(
    service: Any,
    rows: Sequence[Mapping[str, Any]],
    run_id: str,
    *,
    demo: bool = False,
    progress: Callable[[int, int], None] | None = None,
) -> dict[str, dict[str, Any]]:
    """문의를 하나씩 낸다. → {원본 ticket_id: {ticket_id, latency_s, status, error}}.

    한 건이 실패해도 멈추지 않고 error 에 남긴다 (처리 안 된 정답으로 집계된다).
    """
    runs: dict[str, dict[str, Any]] = {}
    for i, row in enumerate(rows, 1):
        gold_id = str(row["ticket_id"])
        started = time.perf_counter()
        try:
            out = service.submit(build_inquiry(row, run_id))
            run = {
                "ticket_id": out.ticket_id,
                "latency_s": round(time.perf_counter() - started, 3),
                "status": str(out.status),
                "error": None,
                "has_draft": getattr(out, "draft", None) is not None,  # 답변 초안 검토 대기인가
            }
        except Exception as e:  # 한 건 실패로 전체 평가를 멈추지 않는다
            run = {
                "ticket_id": None,
                "latency_s": None,
                "status": None,
                "error": _error(e),
            }
        if demo and run["status"] == TicketStatus.READY_FOR_REVIEW:
            # 시연 단계 실패는 평가 결과(처리 여부)와 따로 남긴다
            try:
                gold_reply = _text(row.get("final_reply")) if run["has_draft"] else None
                run["status"] = str(demo_approve(service, run["ticket_id"], gold_reply))
            except Exception as e:
                run["demo_error"] = _error(e)
        run.pop("has_draft", None)
        runs[gold_id] = run
        if progress:
            progress(i, len(rows))
    return runs


def _error(e: Exception) -> str:
    return f"{type(e).__name__}: {e}"[:300]


def demo_approve(service: Any, ticket_id: str, gold_reply: str | None = None) -> TicketStatus:
    """시연: 상담원 대신 실제 회신으로 판단, 답변이 나간 건(승인·이관)만 해결 확정해 사례로 남긴다.

    gold_reply(실제 회신)가 있으면 그 글로 수정 승인, 없으면(추가정보 요청문 등) 그대로 승인.
    추가정보 요청문을 승인하면 고객 회신 대기(WAITING_CUSTOMER)가 되므로 해결하지 않는다.
    """
    if gold_reply:
        review = ReviewIn(
            action=ReviewAction.EDIT_APPROVE,
            reviewer=DEMO_REVIEWER,
            edited_text=gold_reply,
            feedback="시연: 실제 회신으로 수정 승인",
        )
    else:
        review = ReviewIn(action=ReviewAction.APPROVE, reviewer=DEMO_REVIEWER)
    status = service.act(ticket_id, review).status
    if status in (TicketStatus.APPROVED, TicketStatus.ESCALATED):
        status = service.resolve(ticket_id).status
    return status


def fetch_results(
    conn: Any, split: str, runs: Mapping[str, Mapping[str, Any]]
) -> list[dict[str, Any]]:
    """ticket_results 에서 이번 실행 정답만, 이번 실행 티켓 기준으로. + latency_s."""
    from cs_agent.db.queries import run, ticket_results_view

    with ticket_results_view(conn):
        results = run(conn, "eval_join", "ticket_results", split=split)
    mine = {r["ticket_id"] for r in runs.values() if r["ticket_id"]}
    rows = []
    for row in results:
        gold_id = row["gold_ticket_id"]
        if gold_id not in runs:
            continue
        if row["ticket_id"] not in mine:  # 다른 실행의 티켓이 잡히면 처리 안 된 것으로
            row = {
                k: (v if k.startswith("gold") or k in _GOLD_KEYS else None) for k, v in row.items()
            }
        rows.append(
            {**row, "latency_s": runs[gold_id]["latency_s"], "error": runs[gold_id]["error"]}
        )
    return rows


_GOLD_KEYS = {"data_split", "language", "priority_adjusted_by_agent"}


# --- 비교·정리 ------------------------------------------------------------------------------

# (점검 이름, 담당 카드). 앞 단계가 틀리면 뒤 단계는 그 탓이라 앞 단계 카드로 넘긴다.
CHECKS = (
    ("category", "CSA-26"),
    ("dept", "CSA-22"),
    ("priority", "CSA-22"),
    ("missing_info", "CSA-26"),
    ("info_request", "CSA-26"),
    ("evidence", "CSA-28"),
)


def _failed_checks(row: Mapping[str, Any]) -> list[str]:
    failed = []
    if not row.get("category_match"):
        failed.append("category")
    if not row.get("dept_match"):
        failed.append("dept")
    if not row.get("priority_match") and not row.get("priority_adjusted_by_agent"):
        failed.append("priority")
    if not row.get("missing_info_match"):
        failed.append("missing_info")
    if row.get("info_request_sent") != row.get("gold_info_request_sent"):
        failed.append("info_request")
    if row.get("evidence_match") is False:  # 정답 근거가 없으면(None) 보지 않는다
        failed.append("evidence")
    return failed


def mistakes(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """처리됐는데 틀린 건과 처리 못 한 건. 담당 카드(owners)를 붙인다."""
    owner = dict(CHECKS)
    out = []
    for row in rows:
        if row.get("ticket_id") is None:
            out.append(
                {
                    "gold_ticket_id": row["gold_ticket_id"],
                    "failed": ["not_processed"],
                    "owners": ["CSA-50"],
                    "error": row.get("error"),
                }
            )
            continue
        failed = _failed_checks(row)
        if not failed:
            continue
        owners = []
        for check in failed:
            card = owner[check]
            if check in ("dept", "priority") and "category" in failed:
                card = owner["category"]
            if card not in owners:
                owners.append(card)
        out.append(
            {
                "gold_ticket_id": row["gold_ticket_id"],
                "ticket_id": row["ticket_id"],
                "language": row.get("language"),
                "failed": failed,
                "owners": owners,
                "category": [row.get("gold_category"), row.get("category")],
                "dept": [row.get("gold_dept"), row.get("assigned_dept")],
                "priority": [row.get("gold_priority"), row.get("priority")],
                "missing_info": [row.get("gold_missing_info"), row.get("missing_info")],
                "info_request": [row.get("gold_info_request_sent"), row.get("info_request_sent")],
                "evidence": [
                    _ref(row.get("gold_reference_doc_id"), row.get("gold_reference_section")),
                    row.get("evidence_top3"),
                ],
                "status": row.get("status"),
            }
        )
    return out


def _ref(doc_id: str | None, section: str | None) -> str | None:
    return f"{doc_id}#{section}" if doc_id and section else doc_id


def demo_halves(
    rows: Sequence[Mapping[str, Any]], live_cases: Mapping[str, int], order: Sequence[str]
) -> dict[str, dict[str, Any]]:
    """처리 순서 앞 절반 vs 뒤 절반: KPI + live 사례를 근거로 쓴 문의 비율."""
    by_gold = {r["gold_ticket_id"]: r for r in rows}
    ordered = [by_gold[g] for g in order if g in by_gold]
    half = len(ordered) // 2
    result = {}
    for name, part in (("first_half", ordered[:half]), ("second_half", ordered[half:])):
        done = [r for r in part if r.get("ticket_id")]
        used = sum(1 for r in done if live_cases.get(r["ticket_id"], 0) > 0)
        result[name] = without_k2(kpi_report(part)) | {
            "live_case_used": used / len(done) if done else None
        }
    return result


def without_k2(report: dict[str, Any]) -> dict[str, Any]:
    """시연은 실제 회신으로 수정 승인하므로 K2(무수정 승인)를 재지 않는다."""
    return report | {"K2_approve_as_is": None, "K2_note": "시연(--demo)에서는 재지 않음"}


def _table(report: Mapping[str, Any], groups: Mapping[Any, Mapping[str, Any]], label: str) -> str:
    rows = [{"group": "전체", **report}] + [
        {"group": f"{label}={g}", **r} for g, r in groups.items()
    ]
    return markdown_table(rows, REPORT_COLUMNS)


def build_result(
    split: str,
    run_id: str,
    rows: Sequence[Mapping[str, Any]],
    runs: Mapping[str, Mapping[str, Any]],
    demo: dict[str, Any] | None = None,
) -> dict[str, Any]:
    settings = get_settings()
    return {
        "run_id": run_id,
        "split": split,
        "finished_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "settings": {
            "llm_provider": settings.llm_provider,
            "gemini_model_fast": settings.gemini_model_fast,
            "gemini_model_writer": settings.gemini_model_writer,
            "jev_model": settings.jev_model,
            "embedding_model": settings.embedding_model,
        },
        "report": without_k2(kpi_report(rows)) if demo else kpi_report(rows),
        "by_category": by_group(rows, "gold_category"),
        "by_language": by_group(rows, "language"),
        "mistakes": mistakes(rows),
        "errors": {g: r["error"] for g, r in runs.items() if r["error"]},
        "demo_errors": {g: r["demo_error"] for g, r in runs.items() if r.get("demo_error")},
        "demo": demo,
    }


def render_markdown(result: Mapping[str, Any]) -> str:
    report = result["report"]
    lines = [
        f"# 평가 결과 — {result['split']} ({result['run_id']})",
        "",
        f"- 처리 {report['processed']}/{report['gold_count']}건, "
        f"LLM {result['settings']['llm_provider']}, 끝난 시각 {result['finished_at']}",
        f"- K2 무수정 승인(정보 안내형): {report['K2_approve_as_is']} "
        f"(상담원 결정 {report['K2_decided']}건)",
        f"- 목표 통과: {report['checks']}",
        "",
        "## 유형별",
        "",
        _table(report, result["by_category"], "유형"),
        "",
        "## 언어별",
        "",
        _table(report, result["by_language"], "언어"),
        "",
        "## 틀린 건 (담당 카드별)",
        "",
    ]
    by_owner: dict[str, int] = {}
    for m in result["mistakes"]:
        for card in m["owners"]:
            by_owner[card] = by_owner.get(card, 0) + 1
    lines += [f"- {card}: {n}건" for card, n in sorted(by_owner.items())] or ["- 없음"]
    if result.get("demo"):
        lines += ["", "## 시연: 앞 절반 vs 뒤 절반", ""]
        lines.append(
            markdown_table(
                [{"group": k, **v} for k, v in result["demo"].items()],
                REPORT_COLUMNS + ("live_case_used",),
            )
        )
    return "\n".join(lines) + "\n"


def save(result: Mapping[str, Any], out_dir: Path = PROCESSED_DIR) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"eval_{result['split']}_{datetime.now(UTC):%Y%m%d}"
    path = out_dir / f"{stem}.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=1, default=str))
    (out_dir / f"{stem}.md").write_text(render_markdown(result), encoding="utf-8")
    return path


# --- 진입점 ---------------------------------------------------------------------------------


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="시험 문의 평가 (K1~K5)")
    parser.add_argument("--split", default="valid", choices=SPLITS)
    parser.add_argument("--limit", type=int, help="앞에서 N건만 (빠른 확인용)")
    parser.add_argument("--run-id", help="thread_ref 앞에 붙일 실행 ID (기본: eval-시각)")
    parser.add_argument("--demo", action="store_true", help="시연: 승인·해결하며 사례를 쌓는다")
    parser.add_argument("--final", action="store_true", help="test 분할 실행 확인 (N-05)")
    args = parser.parse_args(argv)

    if args.split == "test" and not args.final:
        raise SystemExit("test 597건은 마지막에 한 번만 돌린다 (N-05). 정말 돌리려면 --final")
    if get_settings().llm_provider != "live":
        print("⚠️ LLM_PROVIDER 가 live 가 아니라 실제 성능이 아니다 (파이프라인 확인용)")

    from cs_agent.db.queries import load_tickets_gold, run

    run_id = args.run_id or f"eval-{datetime.now(UTC):%Y%m%d%H%M%S}"
    rows = load_split(args.split)[: args.limit]
    print(f"{args.split} {len(rows)}건 · run_id={run_id}" + (" · 시연" if args.demo else ""))

    def progress(done: int, total: int) -> None:
        if done % 10 == 0 or done == total:
            print(f"  {done}/{total}", flush=True)

    with open_service() as (service, engine):
        with engine.begin() as conn:
            load_tickets_gold(conn)
        runs = submit_all(service, rows, run_id, demo=args.demo, progress=progress)
        with engine.connect() as conn:
            results = fetch_results(conn, args.split, runs)
            demo = None
            if args.demo:
                ids = [r["ticket_id"] for r in runs.values() if r["ticket_id"]]
                live = {
                    r["ticket_id"]: r["live_cases"]
                    for r in run(conn, "eval_join", "live_case_usage", ticket_ids=ids)
                }
                demo = demo_halves(results, live, [str(r["ticket_id"]) for r in rows])

    result = build_result(args.split, run_id, results, runs, demo)
    path = save(result)
    print()
    print(render_markdown(result))
    print(f"저장: {path} (+ .md)")


if __name__ == "__main__":
    main()
