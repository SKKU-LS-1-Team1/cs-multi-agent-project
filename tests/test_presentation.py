import xml.etree.ElementTree as ET

from cs_agent.evaluation.presentation import (
    OUT_DIR,
    bar_svg,
    fmt,
    kpi_table,
    render,
    target_text,
    verdict,
)

FILES = {
    "kpi.svg",
    "category_k3.svg",
    "category_accuracy.svg",
    "language_k3.svg",
    "demo.svg",
    "results.md",
}


def _report(**values):
    base = {
        "processed": 597,
        "gold_count": 597,
        "K1_latency_p95_s": 41.2,
        "K2_approve_as_is": 0.66,
        "K3_evidence_top3": 0.876,
        "K4_dept_accuracy": 0.98,
        "K4_priority_rule_accuracy": 0.777,
        "K5_missing_recall": 0.723,
        "category_accuracy": 0.9,
    }
    return base | values


RESULT = {
    "split": "test",
    "run_id": "eval-1",
    "report": _report(),
    "by_category": {"DEFECT": _report(K3_evidence_top3=0.4), "TECH_SPEC": _report()},
    "by_language": {"en": _report(), "ar": _report(K3_evidence_top3=0.5)},
    "mistakes": [{"owners": ["CSA-26"]}, {"owners": ["CSA-26", "CSA-28"]}],
    "demo": {
        "first_half": {"K3_evidence_top3": 0.55, "live_case_used": 0.05},
        "second_half": {"K3_evidence_top3": 0.63, "live_case_used": 0.41},
    },
}


def test_values_and_verdicts() -> None:
    assert fmt(None, "%") == "—" and fmt(0.8766, "%") == "87.7%" and fmt(41.23, "s") == "41.2초"
    assert target_text("K1_latency_p95_s") == "≤ 60.0초"
    assert target_text("K3_evidence_top3") == "목표 미정"
    assert verdict("K1_latency_p95_s", {"K1_latency_p95_s": 41.2}) == "pass"
    assert verdict("K4_dept_accuracy", {"K4_dept_accuracy": 0.98}) == "fail"  # 게이트 100%
    assert verdict("K3_evidence_top3", {"K3_evidence_top3": 0.9}) == "none"
    assert verdict("K3_evidence_top3", None) == "pending"


def test_empty_template_has_placeholders(tmp_path) -> None:
    written = render(None, out_dir=tmp_path)

    assert {p.name for p in written} == FILES
    for path in written:
        if path.suffix == ".svg":
            ET.parse(path)  # 올바른 SVG(XML)
    assert "평가 후 채움" in (tmp_path / "category_k3.svg").read_text()
    markdown = (tmp_path / "results.md").read_text()
    assert "| K1 처리 지연 p95 | 문의 접수부터 상담원 검토 대기까지 | ≤ 60.0초 | — | 평가 전 |" in (
        markdown
    )
    assert "| 불량 (DEFECT) |" in markdown  # 유형 10개 자리가 미리 있다


def test_filled_from_run_eval_result(tmp_path) -> None:
    render(RESULT, out_dir=tmp_path)

    markdown = (tmp_path / "results.md").read_text()
    assert "test · 처리 597/597건 · eval-1" in markdown
    assert (
        "| K1 처리 지연 p95 | 문의 접수부터 상담원 검토 대기까지 | ≤ 60.0초 | 41.2초 | ✓ 통과 |"
        in (markdown)
    )
    assert "| 98.0% | ✕ 미달 |" in markdown
    assert "| CSA-26 | 문의 분석 | 2건 |" in markdown and "| CSA-28 | 지식 검색 | 1건 |" in markdown
    assert "| 근거 K3 | 55.0% | 63.0% | +8.0%p |" in markdown
    assert "| ar |" in markdown  # 결과에 있는 언어만
    k3 = (tmp_path / "category_k3.svg").read_text()
    assert "<title>불량: 40.0%</title>" in k3 and "평가 후 채움" not in k3
    assert "✓ 통과" in (tmp_path / "kpi.svg").read_text()


def test_bar_length_follows_value_and_target_line() -> None:
    svg = bar_svg("t", [("a", 1.0), ("b", 0.5)], target=0.8)

    paths = ET.fromstring(svg).findall("{http://www.w3.org/2000/svg}path")
    lengths = [float(p.get("d").split(" ")[1].lstrip("h")) for p in paths]
    assert abs(lengths[0] + 4 - 2 * (lengths[1] + 4)) < 0.5  # 값 1.0 막대가 0.5 의 두 배
    assert "목표 80.0%" in svg


def test_committed_template_is_up_to_date(tmp_path) -> None:
    """docs/results 의 빈 틀은 코드로 다시 만든 것과 같아야 한다 (코드만 바꾸고 안 돌린 경우)."""
    render(None, out_dir=tmp_path)

    for name in FILES:
        assert (OUT_DIR / name).read_text() == (tmp_path / name).read_text(), name


def test_kpi_table_lists_every_kpi() -> None:
    table = kpi_table(None)
    assert table.count("\n") == 7  # 머리 2줄 + 지표 6줄
