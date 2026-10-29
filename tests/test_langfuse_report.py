# Langfuse 기록 → 발표용 표 (evaluation/langfuse_report.py). Langfuse 없이 가짜 기록으로
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from cs_agent.evaluation.langfuse_report import (
    fetch,
    first_pass,
    is_real,
    judge_table,
    normalize,
    render,
    stage_table,
    ticket_table,
)

T0 = datetime(2026, 10, 29, 4, 0, tzinfo=UTC)


def _obs(task, model, start_s, latency, *, trace="t1", cost=0.001, **meta):
    start = T0 + timedelta(seconds=start_s)
    return {
        "traceId": trace,
        "name": task,
        "model": model,
        "startTime": start,
        "endTime": start + timedelta(seconds=latency or 0),
        "latency": latency,
        "inputUsage": 100,
        "outputUsage": 20,
        "totalCost": cost,
        "metadata": {"ticket_id": f"T-{trace}", **meta},
    }


def _rows(*observations):
    return [r for r in map(normalize, observations) if is_real(r)]


def test_fake_and_synthetic_models_are_not_counted():
    rows = _rows(
        _obs("classify", "fake", 0, None),
        _obs("llm.extract", "synthetic-local-no-provider", 0, 0.1),
        _obs("classify", "jev-latest", 0, 0.2),
    )
    assert [r["model"] for r in rows] == ["jev-latest"]


def test_stage_table_skips_cache_hits_for_latency_and_flags_slow_calls():
    rows = _rows(
        _obs("draft", "gemini-3.8-flash", 0, 10.0),
        _obs("draft", "gemini-3.8-flash", 20, 90.0),
        _obs("draft", "gemini-3.8-flash", 200, 0.0, cache_hit=True),
        _obs("classify", "jev-latest", 0, 0.2),
    )
    draft, classify = stage_table(rows)  # 느린 단계가 위

    assert (draft["task"], draft["model"], draft["calls"], draft["cache_hits"]) == (
        "draft",
        "Gemini",
        2,
        1,
    )
    assert draft["latency_p50_s"] == 50.0 and draft["over_60s"] == 1
    assert (classify["model"], classify["calls"]) == ("Jev", 1)


def test_judge_table_compares_only_tasks_with_both_models_and_counts_handover():
    rows = _rows(
        _obs("classify", "jev-latest", 0, 0.2),
        _obs("classify", "jev-latest", 10, 0.2),
        _obs(
            "classify",
            "gemini-3.8-flash",
            1,
            5.0,
            fallback_from="jev-latest",
            fallback_reason="low_confidence",
        ),
        _obs("draft", "gemini-3.8-flash", 2, 10.0),  # Gemini 만 → 비교 대상 아님
    )
    gemini, jev = judge_table(rows)

    assert {gemini["task"], jev["task"]} == {"classify"}
    assert (gemini["fallback_low_confidence"], gemini["handed_over_rate"]) == (1, None)
    assert (jev["calls"], jev["handed_over_rate"]) == (2, 0.5)


def test_ticket_time_counts_only_the_first_burst():
    rows = _rows(
        _obs("classify", "jev-latest", 0, 1.0),
        _obs("draft", "gemini-3.8-flash", 2, 20.0, cost=0.01),
        _obs("draft", "gemini-3.8-flash", 3600, 15.0, cost=0.01),  # 한 시간 뒤 재작성
        _obs("classify", "jev-latest", 0, 1.0, trace="t2"),
    )
    assert [c["task"] for c in first_pass(rows[:3])] == ["classify", "draft"]

    (summary,) = ticket_table(rows)
    assert summary["tickets"] == 2
    assert summary["first_pass_p95_s"] <= 22.0  # 재작성 한 시간은 들어가지 않는다
    assert round(summary["cost_total_usd"], 3) == 0.012  # 재작성 비용도 빠진다


def test_fetch_follows_cursor_until_the_end():
    pages = [
        SimpleNamespace(
            data=[_obs("classify", "jev-latest", 0, 0.2)], meta=SimpleNamespace(cursor="c")
        ),
        SimpleNamespace(
            data=[_obs("draft", "gemini-3.8-flash", 1, 9.0)], meta=SimpleNamespace(cursor=None)
        ),
    ]
    calls = []

    def get_many(**kwargs):
        calls.append(kwargs)
        return pages[len(calls) - 1]

    client = SimpleNamespace(api=SimpleNamespace(observations=SimpleNamespace(get_many=get_many)))
    rows = list(fetch(T0, T0 + timedelta(days=1), ["local"], client=client))

    assert [r["task"] for r in rows] == ["classify", "draft"]
    assert [c["cursor"] for c in calls] == [None, "c"]
    assert calls[0]["environment"] == ["local"] and calls[0]["type"] == "GENERATION"


def test_render_has_three_sections():
    text = render([normalize(_obs("classify", "jev-latest", 0, 0.2))], "기록")
    assert (
        "## 단계별 지연" in text and "## Jev vs Gemini" in text and "## 문의 1건당 첫 처리" in text
    )
