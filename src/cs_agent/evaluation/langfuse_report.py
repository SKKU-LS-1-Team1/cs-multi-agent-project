# Langfuse 기록 → 발표용 표 (CSA-48 · 김동규): 단계별 지연 · Jev vs Gemini · 문의 1건당
#
# llm/tracing.py 가 LLM 호출마다 남긴 generation 을 Langfuse API 로 읽어 세 가지 표를 만든다.
#   1. 단계별 지연: 단계(task) × 모델 계열(Jev·Gemini) — 호출 수, p50·p95 지연, 평균 토큰, 비용
#   2. Jev vs Gemini: 두 계열이 모두 불린 판단 단계만 — 기획서 9.2 비교. Gemini 줄의 fallback_* 는
#      Jev 확신도가 낮거나(low_confidence) 실패해서(error) Gemini 로 넘어간 호출 수 (router.judge),
#      Jev 줄의 handed_over_rate 는 그 합 / Jev 호출 수
#   3. 문의 1건당 첫 처리: trace(= ticket_id) 의 호출을 시간순으로 놓고 앞 호출이 끝난 뒤
#      BURST_GAP_S 넘게 쉬면 끊는다. 첫 묶음(접수 직후 처리)의 시작 ~ 끝과 비용. 나중의 재작성·
#      승인·재문의 호출은 같은 trace 에 붙지만 첫 처리 시간에 넣지 않는다.
#
# 정해 둔 것
# - 실제 호출만 센다: 모델이 fake · synthetic-* 이거나 지연이 없는 기록은 뺀다. 캐시에서 꺼낸 호출
#   (metadata.cache_hit)은 지연 계산에서 빼고 건수만 따로 적는다.
# - 기본 환경은 settings.app_env (로컬 = local, VM = prod). 같은 Langfuse 프로젝트에 다른 환경의
#   기록도 섞여 있어서 환경으로 거른다.
# - 60초를 넘는 호출은 over_60s 로 따로 센다. 노트북 잠자기·멈춘 호출이 p95 를 크게 끌어올린다.
# - 문의 1건당 시간은 LLM 호출 구간이다. 검색·규칙·저장 시간까지 넣은 K1 은 run_eval 의 latency_s.
#
# 실행: uv run --extra obs python -m cs_agent.evaluation.langfuse_report --days 7
#   --since 2026-10-20 --until 2026-10-29 (기간), --env local, --out docs/results/langfuse.md
import argparse
from collections import defaultdict
from collections.abc import Iterable, Iterator, Mapping, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from cs_agent.config import get_settings
from cs_agent.evaluation.metrics import markdown_table, model_comparison, percentile

FIELDS = "core,basic,model,usage,metrics,metadata"
PAGE = 1000
SLOW_S = 60.0  # K1 목표 (문의 1건 60초)와 같은 기준
BURST_GAP_S = 120.0  # 같은 문의의 호출이 이만큼 쉬면 다른 처리(재작성·승인 등)로 본다

Row = dict[str, Any]


def _flag(value: Any) -> bool:
    return str(value).lower() == "true"


def family(model: str) -> str:
    name = (model or "").lower()
    if name.startswith("jev"):
        return "Jev"
    if name.startswith("gemini"):
        return "Gemini"
    return model or "-"


def normalize(observation: Mapping[str, Any]) -> Row:
    """Langfuse generation → 표 계산용 행."""
    meta = observation.get("metadata") or {}
    start, end = observation.get("startTime"), observation.get("endTime")
    latency = observation.get("latency")
    return {
        "trace_id": observation.get("traceId"),
        "task": observation.get("name") or "",
        "model": observation.get("model") or observation.get("providedModelName") or "",
        "family": family(observation.get("model") or ""),
        "start": start,
        "end": end,
        "latency_s": float(latency) if latency is not None else None,
        "input_tokens": observation.get("inputUsage") or 0,
        "output_tokens": observation.get("outputUsage") or 0,
        "cost_usd": float(observation.get("totalCost") or 0.0),
        "cache_hit": _flag(meta.get("cache_hit")),
        "fallback_from": meta.get("fallback_from") or None,
        "fallback_reason": meta.get("fallback_reason") or None,
        "ticket_id": meta.get("ticket_id") or None,
    }


def is_real(row: Mapping[str, Any]) -> bool:
    """모델을 실제로 부른 기록 (fake · 합성 · 지연 없는 기록 제외)."""
    model = row["model"].lower()
    return bool(model) and model != "fake" and not model.startswith("synthetic")


def fetch(
    since: datetime, until: datetime, environments: Sequence[str], client: Any = None
) -> Iterator[Row]:
    """기간 안의 generation 기록 (cursor 로 끝까지)."""
    if client is None:
        from cs_agent.llm.tracing import _client

        client = _client()
        if client is None:
            raise SystemExit(
                "Langfuse 키나 패키지가 없다 (.env 의 LANGFUSE_* · uv sync --extra obs)"
            )
    cursor = None
    while True:
        page = client.api.observations.get_many(
            type="GENERATION",
            fields=FIELDS,
            environment=list(environments),
            from_start_time=since,
            to_start_time=until,
            limit=PAGE,
            cursor=cursor,
        )
        for observation in page.data:
            yield normalize(observation if isinstance(observation, Mapping) else observation.dict())
        cursor = page.meta.cursor if page.meta else None
        if not cursor or not page.data:
            return


# 표 ---------------------------------------------------------------------------------------------

STAGE_COLUMNS = (
    "task",
    "model",
    "calls",
    "cache_hits",
    "latency_p50_s",
    "latency_p95_s",
    "over_60s",
    "input_tokens_avg",
    "output_tokens_avg",
    "cost_usd",
)
JUDGE_COLUMNS = (
    "task",
    "model",
    "calls",
    "fallback_low_confidence",
    "fallback_error",
    "handed_over_rate",
    "latency_p50_s",
    "latency_p95_s",
    "cost_per_call_usd",
)
TICKET_COLUMNS = (
    "tickets",
    "llm_calls_avg",
    "first_pass_p50_s",
    "first_pass_p95_s",
    "over_60s",
    "cost_avg_usd",
    "cost_total_usd",
)


def _avg(values: Sequence[float]) -> float | None:
    return sum(values) / len(values) if values else None


def stage_table(rows: Iterable[Mapping[str, Any]]) -> list[Row]:
    """단계 × 모델 계열. 지연·토큰은 캐시가 아닌 호출로만 잰다. 느린 단계(p95)가 위."""
    groups: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[(row["task"], row["family"])].append(row)
    table = []
    for (task, model), calls in groups.items():
        live = [c for c in calls if not c["cache_hit"] and c["latency_s"] is not None]
        latencies = [c["latency_s"] for c in live]
        table.append(
            {
                "task": task,
                "model": model,
                "calls": len(live),
                "cache_hits": len(calls) - len(live),
                "latency_p50_s": percentile(latencies, 50),
                "latency_p95_s": percentile(latencies, 95),
                "over_60s": sum(x > SLOW_S for x in latencies),
                "input_tokens_avg": _avg([c["input_tokens"] for c in live]),
                "output_tokens_avg": _avg([c["output_tokens"] for c in live]),
                "cost_usd": sum(c["cost_usd"] for c in live),
            }
        )
    return sorted(table, key=lambda r: (-(r["latency_p95_s"] or 0), r["task"], r["model"]))


def judge_table(rows: Iterable[Mapping[str, Any]]) -> list[Row]:
    """Jev · Gemini 가 모두 불린 단계만, 단계마다 두 계열을 나란히 (metrics.model_comparison)."""
    by_task: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        if not row["cache_hit"] and row["latency_s"] is not None:
            by_task[row["task"]].append(row)
    table = []
    for task in sorted(by_task):
        calls = by_task[task]
        if {c["family"] for c in calls} < {"Jev", "Gemini"}:
            continue
        handed = sum(1 for c in calls if c["family"] == "Gemini" and c["fallback_from"])
        compared = model_comparison(
            {"model": c["family"], "latency_s": c["latency_s"], "cost_usd": c["cost_usd"]}
            for c in calls
            if c["family"] in ("Jev", "Gemini")
        )
        for result in compared:
            mine = [c for c in calls if c["family"] == result["model"]]
            jev = result["model"] == "Jev"
            table.append(
                {
                    "task": task,
                    "model": result["model"],
                    "calls": result["calls"],
                    "fallback_low_confidence": sum(
                        c["fallback_reason"] == "low_confidence" for c in mine
                    ),
                    "fallback_error": sum(c["fallback_reason"] == "error" for c in mine),
                    "handed_over_rate": handed / result["calls"] if jev else None,
                    "latency_p50_s": result["latency_p50_s"],
                    "latency_p95_s": result["latency_p95_s"],
                    "cost_per_call_usd": result["cost_usd"] / result["calls"],
                }
            )
    return table


def first_pass(calls: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    """한 문의의 호출 중 첫 묶음 (앞 호출들이 끝난 뒤 BURST_GAP_S 넘게 쉬면 끊는다)."""
    ordered = sorted(calls, key=lambda c: _time(c["start"]))
    burst = ordered[:1]
    end = _time(ordered[0]["end"]) if ordered else None
    for call in ordered[1:]:
        if (_time(call["start"]) - end).total_seconds() > BURST_GAP_S:
            break
        burst.append(call)
        end = max(end, _time(call["end"]))
    return burst


def ticket_table(rows: Iterable[Mapping[str, Any]]) -> list[Row]:
    """문의(trace)마다 첫 처리 묶음의 시작 ~ 끝, 호출 수, 비용."""
    traces: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        if row["ticket_id"] and not row["cache_hit"] and row["start"] and row["end"]:
            traces[row["trace_id"]].append(row)
    spans, costs, counts = [], [], []
    for calls in traces.values():
        burst = first_pass(calls)
        start = min(_time(c["start"]) for c in burst)
        end = max(_time(c["end"]) for c in burst)
        spans.append((end - start).total_seconds())
        costs.append(sum(c["cost_usd"] for c in burst))
        counts.append(len(burst))
    return [
        {
            "tickets": len(spans),
            "llm_calls_avg": _avg(counts),
            "first_pass_p50_s": percentile(spans, 50),
            "first_pass_p95_s": percentile(spans, 95),
            "over_60s": sum(x > SLOW_S for x in spans),
            "cost_avg_usd": _avg(costs),
            "cost_total_usd": sum(costs),
        }
    ]


def _time(value: Any) -> datetime:
    return value if isinstance(value, datetime) else datetime.fromisoformat(str(value))


def render(rows: Sequence[Mapping[str, Any]], title: str) -> str:
    real = [r for r in rows if is_real(r)]
    return "\n".join(
        [
            f"# {title}",
            "",
            f"- 실제 LLM 호출 {len(real)}건 (전체 기록 {len(rows)}건, fake·합성 제외)",
            "- 지연·토큰은 캐시가 아닌 호출만. 지연 단위 초, 비용 USD (Langfuse 모델 단가)",
            "",
            "## 단계별 지연 (느린 순)",
            "",
            markdown_table(stage_table(real), STAGE_COLUMNS),
            "",
            "## Jev vs Gemini (둘 다 불린 판단 단계)",
            "",
            "Gemini 줄의 fallback_* = Jev 확신도가 낮거나 실패해서 Gemini 로 넘어간 호출 수, "
            "Jev 줄의 handed_over_rate = 그 합 / Jev 호출 수.",
            "",
            markdown_table(judge_table(real), JUDGE_COLUMNS),
            "",
            "## 문의 1건당 첫 처리 (LLM 구간)",
            "",
            f"접수 직후 호출 묶음(호출 사이 {BURST_GAP_S:.0f}초 넘게 쉬면 끊음)의 시작 ~ 끝. "
            "검색·규칙·저장까지 넣은 K1 은 run_eval 로 잰다.",
            "",
            markdown_table(ticket_table(real), TICKET_COLUMNS),
            "",
        ]
    )


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Langfuse 기록 → 단계별 지연 · Jev vs Gemini 표")
    parser.add_argument("--days", type=float, default=7, help="최근 며칠 (기본 7)")
    parser.add_argument("--since", type=datetime.fromisoformat, help="시작 (예: 2026-10-20)")
    parser.add_argument("--until", type=datetime.fromisoformat, help="끝 (기본: 지금)")
    parser.add_argument(
        "--env", action="append", help="Langfuse 환경 (여러 번 가능, 기본: APP_ENV)"
    )
    parser.add_argument("--out", type=Path, help="마크다운 저장 경로")
    args = parser.parse_args(argv)

    until = (args.until or datetime.now(UTC)).astimezone(UTC)
    since = (args.since or until - timedelta(days=args.days)).astimezone(UTC)
    environments = args.env or [get_settings().app_env]
    rows = list(fetch(since, until, environments))
    title = f"LLM 호출 기록 ({', '.join(environments)} · {since:%Y-%m-%d} ~ {until:%Y-%m-%d})"
    text = render(rows, title)
    print(text)
    if args.out:
        args.out.write_text(text, encoding="utf-8")
        print(f"저장: {args.out}")


if __name__ == "__main__":
    main()
