# KPI 계산 (CSA-49 기준선 측정 · 담당 김동규 · Sprint 1)
#
# 정의·목표치는 analysis/kpi/KPI_설정안.md 를 따른다.
#   K1 처리 지연 p95 (목표 ≤ 60초, run_eval 이 잰 latency_s. 단계별 LLM 지연은 langfuse_report)
#   K2 무수정 승인 가능률 (정보 안내형)
#   K3 근거 일치율 (reference_doc_id + reference_section)
#   K4 부서·우선순위 일치율 (부서는 100% 게이트)
#   K5 필수정보 누락 탐지율 (missing_info 재현율)
#
# 할 일
# 1. accuracy(pred, gold), p95(values), recall(pred_sets, gold_sets) 같은 계산 함수
# 2. 기준선: valid 603건으로 현재 값을 재고 목표치를 확정해 KPI_설정안.md 에 기록
# 3. Jev vs Gemini 비교 (정확도·응답 시간·비용) 표 (기획서 9.2)
#
# 정해 둔 것
# - 입력 행 = eval.ticket_results 뷰 한 행(db/sql/eval_join.sql) + run_eval 이 잰 latency_s.
#   kpi_report(rows) 가 K1~K5 를, by_group(rows, "gold_category"|"language") 가 묶음별 값을 낸다.
# - 분모는 eval_summary SQL 과 같다: 시스템 티켓이 있는(처리된) 정답만, 비교가 비어(NULL) 있으면
#   틀린 것. 근거 일치(K3)만 정답 근거가 없는 문의를 뺀다.
# - K2 = 정보 안내형(domain.BUNDLE_OF) 정답 중 상담원이 결정한 건(그대로 승인·수정 후 승인·반려)에서
#   그대로 승인 비율. 상담원 검토가 없으면 None.
# - K4 우선순위는 상담원 조정 정답(priority_adjusted_by_agent)을 뺀 규칙 일치율도 같이 낸다.
# - 백분위는 numpy 기본(선형 보간)과 같은 값을 낸다. 값이 없으면 None.
# - 목표치(TARGETS)는 K1·K4 부서만 정해져 있다. 나머지는 할 일 2 기준선을 잰 뒤 채운다.
#
# 할 일 2 는 실제 시스템(LLM 키)으로 valid 를 돌려야 해서 이 파일 밖이다 (run_eval, CSA-50).
#
#   report = kpi_report(rows)              # {"K1_latency_p95_s": 41.2, ..., "checks": {...}}
#   print(markdown_table(model_comparison(calls), MODEL_COLUMNS))
from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Any

from cs_agent.domain import BUNDLE_OF, Bundle

DECISIONS = ("approve", "edit_approve", "reject")  # 상담원 결정 버튼 (dept_dashboard.sql 과 같다)
INFO_CATEGORIES = frozenset(str(c) for c, b in BUNDLE_OF.items() if b == Bundle.INFO)

# 목표 (KPI_설정안.md). (비교, 값): "max" 는 이하, "min" 은 이상이면 통과.
# None 은 기준선 측정 후 확정 (할 일 2)
TARGETS: dict[str, tuple[str, float] | None] = {
    "K1_latency_p95_s": ("max", 60.0),
    "K2_approve_as_is": None,
    "K3_evidence_top3": None,
    "K4_dept_accuracy": ("min", 1.0),  # 게이트
    "K4_priority_accuracy": None,
    "K5_missing_recall": None,
}


# --- 계산 함수 (할 일 1) ----------------------------------------------------------------------


def accuracy(pred: Sequence[Any], gold: Sequence[Any]) -> float | None:
    """같은 위치끼리 일치 비율. 예측이 None 이면 틀린 것. 비어 있으면 None."""
    if len(pred) != len(gold):
        raise ValueError(f"길이가 다르다: pred {len(pred)}, gold {len(gold)}")
    if not gold:
        return None
    return sum(p is not None and p == g for p, g in zip(pred, gold, strict=True)) / len(gold)


def share(flags: Iterable[bool | None], *, none_is: bool | None = None) -> float | None:
    """True 비율. None 은 none_is 로 보고, none_is 도 None 이면 분모에서 뺀다."""
    values = [none_is if f is None else bool(f) for f in flags]
    values = [v for v in values if v is not None]
    return sum(values) / len(values) if values else None


def percentile(values: Iterable[float], q: float) -> float | None:
    """q(0~100) 백분위. numpy.percentile 기본(선형 보간)과 같다."""
    data = sorted(float(v) for v in values if v is not None)
    if not data:
        return None
    if not 0 <= q <= 100:
        raise ValueError(f"q 는 0~100: {q}")
    pos = (len(data) - 1) * q / 100
    lo = int(pos)
    hi = min(lo + 1, len(data) - 1)
    return data[lo] + (data[hi] - data[lo]) * (pos - lo)


def p95(values: Iterable[float]) -> float | None:
    return percentile(values, 95)


def recall(pred_sets: Sequence[Iterable[str]], gold_sets: Sequence[Iterable[str]]) -> float | None:
    """전체 합산 재현율: 찾은 정답 항목 수 / 정답 항목 수. 정답 항목이 하나도 없으면 None."""
    if len(pred_sets) != len(gold_sets):
        raise ValueError(f"길이가 다르다: pred {len(pred_sets)}, gold {len(gold_sets)}")
    found = total = 0
    for pred, gold in zip(pred_sets, gold_sets, strict=True):
        gold = set(gold)
        found += len(gold & set(pred or ()))
        total += len(gold)
    return found / total if total else None


def top_k_hit(
    cited: Sequence[str], doc_id: str | None, section: str | None = None, k: int = 3
) -> bool | None:
    """근거 상위 k개("doc_id#section" 또는 "doc_id")에 정답 문서(절이 있으면 절까지)가 있나.

    정답 근거가 없는 문의는 None (K3 분모에서 뺀다).
    """
    if not doc_id:
        return None
    for ref in list(cited)[:k]:
        ref_doc, _, ref_section = ref.partition("#")
        if ref_doc == doc_id and (not section or ref_section == section):
            return True
    return False


# --- KPI 묶음 -------------------------------------------------------------------------------


def _processed(rows: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    return [r for r in rows if r.get("ticket_id") is not None]


def kpi_report(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """eval.ticket_results 행(+ latency_s) → K1~K5 와 목표 통과 여부."""
    done = _processed(rows)
    info_decided = [
        r
        for r in done
        if r.get("gold_category") in INFO_CATEGORIES and r.get("review_action") in DECISIONS
    ]
    rule_rows = [r for r in done if not r.get("priority_adjusted_by_agent")]
    found = sum(r.get("missing_found_count") or 0 for r in done)
    gold_missing = sum(r.get("gold_missing_count") or 0 for r in done)

    report: dict[str, Any] = {
        "gold_count": len(rows),
        "processed": len(done),
        "K1_latency_p95_s": p95(r["latency_s"] for r in done if r.get("latency_s") is not None),
        "K2_approve_as_is": share(r["review_action"] == "approve" for r in info_decided),
        "K2_decided": len(info_decided),
        "K3_evidence_top3": share(r.get("evidence_match") for r in done),
        "K4_dept_accuracy": share((r.get("dept_match") for r in done), none_is=False),
        "K4_priority_accuracy": share((r.get("priority_match") for r in done), none_is=False),
        "K4_priority_rule_accuracy": share(
            (r.get("priority_match") for r in rule_rows), none_is=False
        ),
        "K5_missing_recall": found / gold_missing if gold_missing else None,
        "category_accuracy": share((r.get("category_match") for r in done), none_is=False),
    }
    report["checks"] = check_targets(report)
    return report


def check_targets(report: Mapping[str, Any]) -> dict[str, bool | None]:
    """목표가 정해진 KPI 만 통과 여부. 값이 없으면 None."""
    checks: dict[str, bool | None] = {}
    for name, target in TARGETS.items():
        if target is None:
            continue
        kind, goal = target
        value = report.get(name)
        checks[name] = (
            None if value is None else (value <= goal if kind == "max" else value >= goal)
        )
    return checks


def by_group(
    rows: Sequence[Mapping[str, Any]],
    key: str | Callable[[Mapping[str, Any]], Any],
) -> dict[Any, dict[str, Any]]:
    """행을 key(열 이름 또는 함수)로 묶어 묶음마다 kpi_report. 유형별·언어별 분석용."""
    get = (lambda r: r.get(key)) if isinstance(key, str) else key
    groups: dict[Any, list[Mapping[str, Any]]] = defaultdict(list)
    for r in rows:
        groups[get(r)].append(r)
    return {g: kpi_report(groups[g]) for g in sorted(groups, key=lambda g: (g is None, str(g)))}


# --- Jev vs Gemini 비교 (할 일 3) -------------------------------------------------------------

MODEL_COLUMNS = ("model", "calls", "accuracy", "latency_p50_s", "latency_p95_s", "cost_usd")


def model_comparison(calls: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """판단 호출 기록 → 모델별 정확도·지연·비용.

    calls 한 행: {"model", "latency_s", "correct"(정답 일치, 모르면 None), "cost_usd"(없으면 0)}.
    Langfuse generation 기록이나 같은 문의를 두 모델에 돌린 결과를 이 모양으로 넘긴다.
    """
    by_model: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for c in calls:
        by_model[c["model"]].append(c)
    table = []
    for model in sorted(by_model):
        rows = by_model[model]
        latencies = [r["latency_s"] for r in rows if r.get("latency_s") is not None]
        table.append(
            {
                "model": model,
                "calls": len(rows),
                "accuracy": share(r.get("correct") for r in rows),
                "latency_p50_s": percentile(latencies, 50),
                "latency_p95_s": p95(latencies),
                "cost_usd": sum(r.get("cost_usd") or 0.0 for r in rows),
            }
        )
    return table


def markdown_table(rows: Sequence[Mapping[str, Any]], columns: Sequence[str]) -> str:
    """보고서·KPI_설정안.md 에 붙일 표. 실수는 소수 셋째 자리, None 은 '-'."""

    def cell(v: Any) -> str:
        if v is None:
            return "-"
        if isinstance(v, float):
            return f"{v:.3f}"
        return str(v)

    lines = [
        "| " + " | ".join(columns) + " |",
        "|" + "|".join("---" for _ in columns) + "|",
    ]
    lines += ["| " + " | ".join(cell(r.get(c)) for c in columns) + " |" for r in rows]
    return "\n".join(lines)
