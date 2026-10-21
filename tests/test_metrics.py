import pytest

from cs_agent.evaluation.metrics import (
    MODEL_COLUMNS,
    accuracy,
    by_group,
    kpi_report,
    markdown_table,
    model_comparison,
    p95,
    percentile,
    recall,
    share,
    top_k_hit,
)


def test_accuracy_counts_missing_prediction_as_wrong() -> None:
    assert accuracy(["A", None, "C", "D"], ["A", "B", "C", "X"]) == 0.5
    assert accuracy([], []) is None
    with pytest.raises(ValueError):
        accuracy(["A"], ["A", "B"])


def test_share_none_handling() -> None:
    assert share([True, False, None]) == 0.5  # None 은 뺀다
    assert share([True, False, None], none_is=False) == pytest.approx(1 / 3)
    assert share([None]) is None


def test_percentile_matches_numpy_linear() -> None:
    values = [10, 1, 7, 3, 5]
    assert percentile(values, 50) == 5
    assert percentile(values, 0) == 1 and percentile(values, 100) == 10
    assert p95(values) == pytest.approx(9.4)  # numpy.percentile([1,3,5,7,10], 95)
    assert p95(range(1, 101)) == pytest.approx(95.05)
    assert p95([]) is None


def test_recall_is_pooled_over_tickets() -> None:
    pred = [["serial_no"], [], ["photos", "extra"]]
    gold = [["serial_no", "photos"], ["fw_version"], ["photos"]]
    assert recall(pred, gold) == 0.5  # 4개 중 2개
    assert recall([[]], [[]]) is None


def test_top_k_hit_checks_section_when_given() -> None:
    cited = ["DS-1#2.1", "TG-1#3.1", "POL-1#2", "TG-2#1"]
    assert top_k_hit(cited, "TG-1", "3.1") is True
    assert top_k_hit(cited, "TG-1", "4") is False
    assert top_k_hit(cited, "POL-1") is True  # 절이 없으면 문서만
    assert top_k_hit(cited, "TG-2") is False  # 4번째라 상위 3개 밖
    assert top_k_hit(cited, None) is None


def _row(gold_id: str, **values) -> dict:
    return {
        "gold_ticket_id": gold_id,
        "ticket_id": f"T-{gold_id}",
        "gold_category": "TECH_SPEC",
        "language": "en",
        "category_match": True,
        "dept_match": True,
        "priority_match": True,
        "priority_adjusted_by_agent": False,
        "missing_found_count": 0,
        "gold_missing_count": 0,
        "evidence_match": True,
        "review_action": None,
        "latency_s": 10.0,
    } | values


def test_kpi_report_uses_processed_tickets_and_counts_empty_as_wrong() -> None:
    rows = [
        _row("G1", review_action="approve", missing_found_count=1, gold_missing_count=2),
        _row("G2", review_action="edit_approve", latency_s=70.0, evidence_match=None),
        # 분석 실패: 비교가 비었다 → 틀린 것
        _row(
            "G3",
            gold_category="DEFECT",
            category_match=None,
            dept_match=None,
            priority_match=None,
            evidence_match=False,
            review_action="approve",  # 정보 안내형이 아니라 K2 에서 빠진다
            gold_missing_count=2,
        ),
        _row("G4", priority_match=False, priority_adjusted_by_agent=True),
        _row("G5", ticket_id=None, latency_s=None),  # 처리 안 됨 → 분모에서 빠진다
    ]

    report = kpi_report(rows)

    assert (report["gold_count"], report["processed"]) == (5, 4)
    assert report["K1_latency_p95_s"] == pytest.approx(61.0)
    assert (report["K2_approve_as_is"], report["K2_decided"]) == (0.5, 2)
    assert report["K3_evidence_top3"] == pytest.approx(2 / 3)  # 정답 근거 없는 G2 는 뺀다
    assert report["K4_dept_accuracy"] == 0.75
    assert report["K4_priority_accuracy"] == 0.5
    assert report["K4_priority_rule_accuracy"] == pytest.approx(2 / 3)  # 상담원 조정 G4 는 뺀다
    assert report["K5_missing_recall"] == 0.25
    assert report["category_accuracy"] == 0.75
    assert report["checks"] == {"K1_latency_p95_s": False, "K4_dept_accuracy": False}


def test_kpi_report_without_reviews_or_rows() -> None:
    report = kpi_report([_row("G1")])
    assert report["K2_approve_as_is"] is None and report["K2_decided"] == 0
    assert report["checks"] == {"K1_latency_p95_s": True, "K4_dept_accuracy": True}

    empty = kpi_report([])
    assert empty["processed"] == 0 and empty["K4_dept_accuracy"] is None
    assert empty["checks"] == {"K1_latency_p95_s": None, "K4_dept_accuracy": None}


def test_by_group_splits_rows() -> None:
    rows = [_row("G1"), _row("G2", language="ko", dept_match=False)]

    groups = by_group(rows, "language")

    assert list(groups) == ["en", "ko"]
    assert groups["ko"]["K4_dept_accuracy"] == 0.0 and groups["en"]["K4_dept_accuracy"] == 1.0
    bundle = by_group(rows, lambda r: r["gold_category"][:4])
    assert list(bundle) == ["TECH"]


def test_model_comparison_table() -> None:
    calls = [
        {"model": "jev-1.13.0", "latency_s": 1.0, "correct": True, "cost_usd": 0.001},
        {"model": "jev-1.13.0", "latency_s": 3.0, "correct": False, "cost_usd": 0.001},
        {"model": "gemini-3.7-flash", "latency_s": 4.0, "correct": True},
        {"model": "gemini-3.7-flash", "latency_s": None, "correct": None, "cost_usd": 0.01},
    ]

    table = model_comparison(calls)

    assert [r["model"] for r in table] == ["gemini-3.7-flash", "jev-1.13.0"]
    gemini, jev = table
    assert (gemini["calls"], gemini["accuracy"], gemini["latency_p95_s"]) == (2, 1.0, 4.0)
    assert jev["accuracy"] == 0.5 and jev["latency_p50_s"] == 2.0
    assert jev["cost_usd"] == pytest.approx(0.002)

    text = markdown_table(table, MODEL_COLUMNS)
    assert text.splitlines()[0] == "| " + " | ".join(MODEL_COLUMNS) + " |"
    assert "| jev-1.13.0 | 2 | 0.500 | 2.000 |" in text
