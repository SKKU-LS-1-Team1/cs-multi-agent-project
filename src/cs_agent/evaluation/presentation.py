# 발표용 결과 표·그래프 (CSA-51 · 담당 박종석) — 최종 시험 결과 정리 (MVP 시연용)
# 실행 예:
#   uv run python -m cs_agent.evaluation.presentation                       # 빈 틀 (숫자 "—")
#   uv run python -m cs_agent.evaluation.presentation data/processed/eval_test_20261101.json
#   run_eval 결과 JSON 을 넘기면 숫자를 채운다. 시연 비교는 --demo 로 돌린 결과 JSON 을
#   --demo-result 로 따로 넘길 수 있다.
#
# 출력 (docs/results/, 슬라이드에 그대로 붙인다)
# - results.md          K1~K5 표, 유형별·언어별 표, 틀린 건 담당 카드별, 시연 앞/뒤 표 + 그래프 링크
# - kpi.svg             K1~K5 숫자 카드 (값 · 목표 · 통과 여부)
# - category_k3.svg     유형별 근거 일치율(K3) 가로 막대
# - category_accuracy.svg 유형별 분류 정확도
# - language_k3.svg     언어별 근거 일치율(K3)
# - demo.svg            시연: 앞 절반 vs 뒤 절반 (비율 지표만)
#
# 정해 둔 것 (그래프 규칙은 dataviz 방법을 따른다)
# - K1~K5 는 단위가 달라(초·비율) 한 축 막대로 그리지 않고 숫자 카드로 둔다. 통과 여부는 색만이
#   아니라 아이콘 + 글자(✓ 통과 / ✕ 미달 / – 목표 미정)로 보인다.
# - 막대는 한 가지 지표 = 한 그래프(범례 없음, 값은 막대 끝). 목표가 있으면 점선으로.
#   시연 비교만 두 계열(앞·뒤, 파랑·주황 — 팔레트 검증 통과)이라 범례 + 값 표시.
# - 글자는 잉크 색(primary/secondary/muted)만 쓴다. 막대 색을 글자에 쓰지 않는다.
# - 슬라이드가 밝은 배경이라 라이트 팔레트만. 막대마다 <title> 이 있어 SVG 를 열면 값이 뜬다.
# - 지표 정의·목표는 evaluation/metrics.py (TARGETS). 목표가 None 인 지표는 "목표 미정".
import argparse
import json
import math
from collections.abc import Mapping, Sequence
from html import escape
from pathlib import Path
from typing import Any

from cs_agent.config import REPO_ROOT
from cs_agent.domain import Category
from cs_agent.evaluation.metrics import TARGETS

OUT_DIR = REPO_ROOT / "docs" / "results"
PENDING = "—"

# 팔레트 (dataviz 기준 팔레트, 라이트)
INK = {"primary": "#0b0b0b", "secondary": "#52514e", "muted": "#898781"}
GRID, AXIS, SURFACE, BORDER = "#e1e0d9", "#c3c2b7", "#fcfcfb", "rgba(11,11,11,0.10)"
SERIES = ("#2a78d6", "#eb6834")  # 파랑·주황 — validate_palette.js 통과 (CVD ΔE 24.7)
STATUS = {"pass": "#0ca30c", "fail": "#d03b3b"}
FONT = "Pretendard, 'Noto Sans KR', 'Apple SD Gothic Neo', sans-serif"

# (보고서 키, 카드 제목, 한 줄 뜻, 단위)
KPIS: tuple[tuple[str, str, str, str], ...] = (
    ("K1_latency_p95_s", "K1 처리 지연 p95", "문의 접수부터 상담원 검토 대기까지", "s"),
    ("K2_approve_as_is", "K2 무수정 승인", "정보 안내형 초안을 고치지 않고 승인", "%"),
    ("K3_evidence_top3", "K3 근거 일치", "정답 문서·절이 근거 상위 3개 안", "%"),
    ("K4_dept_accuracy", "K4 부서 일치", "담당 부서 배정 (게이트)", "%"),
    ("K4_priority_rule_accuracy", "K4 우선순위 일치", "상담원 조정 건 제외 규칙 일치", "%"),
    ("K5_missing_recall", "K5 누락 탐지", "빠진 필수정보를 찾아낸 비율", "%"),
)
GROUP_COLUMNS: tuple[tuple[str, str, str], ...] = (
    ("processed", "처리", "n"),
    ("category_accuracy", "유형", "%"),
    ("K3_evidence_top3", "근거 K3", "%"),
    ("K4_dept_accuracy", "부서 K4", "%"),
    ("K4_priority_rule_accuracy", "우선순위 K4", "%"),
    ("K5_missing_recall", "누락 K5", "%"),
    ("K1_latency_p95_s", "지연 p95", "s"),
)
CATEGORY_KO = {
    "TECH_SPEC": "사양",
    "MANUAL": "매뉴얼",
    "COMPLIANCE": "인증·규격",
    "QUOTE": "견적",
    "ORDER_LEAD": "주문·납기",
    "DEFECT": "불량",
    "INSTALL": "설치",
    "FW_UPDATE": "펌웨어",
    "WARRANTY": "보증",
    "RETURN": "반품",
}
DEMO_METRICS = (  # 비율 지표만 (K1 초는 한 축에 못 둔다)
    ("category_accuracy", "유형"),
    ("K3_evidence_top3", "근거 K3"),
    ("K4_dept_accuracy", "부서 K4"),
    ("K5_missing_recall", "누락 K5"),
    ("live_case_used", "live 사례 사용"),
)
OWNERS = {
    "CSA-22": "규칙 처리",
    "CSA-26": "문의 분석",
    "CSA-28": "지식 검색",
    "CSA-50": "처리 실패",
}


# --- 값 ---------------------------------------------------------------------------------------


def fmt(value: Any, unit: str) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return PENDING
    if unit == "%":
        return f"{value * 100:.1f}%"
    if unit == "s":
        return f"{value:.1f}초"
    return f"{value:,}"


def target_text(key: str) -> str:
    target = TARGETS.get(key)
    if target is None:
        return "목표 미정"
    kind, goal = target
    unit = "s" if key.endswith("_s") else "%"
    return f"{'≤' if kind == 'max' else '≥'} {fmt(goal, unit)}"


def verdict(key: str, report: Mapping[str, Any] | None) -> str:
    """'pass' / 'fail' / 'none'(목표 미정) / 'pending'(평가 전)."""
    value = (report or {}).get(key)
    if value is None:
        return "pending"
    if TARGETS.get(key) is None:
        return "none"
    kind, goal = TARGETS[key]
    return "pass" if (value <= goal if kind == "max" else value >= goal) else "fail"


VERDICT_TEXT = {"pass": "✓ 통과", "fail": "✕ 미달", "none": "– 목표 미정", "pending": "평가 전"}


# --- 표 (Markdown) ----------------------------------------------------------------------------


def _md(rows: Sequence[Sequence[str]], header: Sequence[str]) -> str:
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(r) + " |" for r in rows]
    return "\n".join(lines)


def kpi_table(report: Mapping[str, Any] | None) -> str:
    rows = [
        (
            title,
            desc,
            target_text(key),
            fmt((report or {}).get(key), unit),
            VERDICT_TEXT[verdict(key, report)],
        )
        for key, title, desc, unit in KPIS
    ]
    return _md(rows, ("지표", "뜻", "목표", "결과", "판정"))


def group_table(
    groups: Mapping[str, Mapping[str, Any]] | None,
    label: str,
    names: Sequence[str],
    ko: Mapping[str, str] | None = None,
) -> str:
    groups = groups or {}
    keys = (
        list(names)
        if not groups
        else [g for g in names if g in groups] + [g for g in groups if g not in names]
    )
    rows = []
    for g in keys:
        r = groups.get(g, {})
        name = f"{(ko or {}).get(g, g)} ({g})" if ko and g in ko else str(g)
        rows.append((name, *(fmt(r.get(k), unit) for k, _, unit in GROUP_COLUMNS)))
    return _md(rows, (label, *(title for _, title, _ in GROUP_COLUMNS)))


def owner_table(mistakes: Sequence[Mapping[str, Any]] | None) -> str:
    counts = dict.fromkeys(OWNERS, 0)
    for m in mistakes or []:
        for card in m.get("owners", []):
            counts[card] = counts.get(card, 0) + 1
    done = mistakes is not None
    rows = [
        (card, OWNERS.get(card, ""), f"{n}건" if done else PENDING) for card, n in counts.items()
    ]
    return _md(rows, ("담당 카드", "단계", "틀린 건"))


def demo_table(demo: Mapping[str, Mapping[str, Any]] | None) -> str:
    first = (demo or {}).get("first_half", {})
    second = (demo or {}).get("second_half", {})
    rows = []
    for key, title in DEMO_METRICS:
        a, b = first.get(key), second.get(key)
        change = PENDING if a is None or b is None else f"{(b - a) * 100:+.1f}%p"
        rows.append((title, fmt(a, "%"), fmt(b, "%"), change))
    return _md(rows, ("지표", "앞 절반", "뒤 절반", "변화"))


# --- 그래프 (SVG) -----------------------------------------------------------------------------


def _svg(width: int, height: int, title: str, body: Sequence[str]) -> str:
    return "\n".join(
        [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}" font-family="{escape(FONT)}" role="img">',
            f"<title>{escape(title)}</title>",
            f'<rect width="{width}" height="{height}" fill="{SURFACE}"/>',
            *body,
            "</svg>",
        ]
    )


def _text(
    x: float,
    y: float,
    text: str,
    size: int = 14,
    ink: str = "secondary",
    anchor: str = "start",
    weight: int = 400,
) -> str:
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" fill="{INK[ink]}" '
        f'text-anchor="{anchor}" font-weight="{weight}">{escape(text)}</text>'
    )


def _bar(x: float, y: float, w: float, h: float, color: str, tip: str) -> str:
    """기준선 쪽은 각지고 값 끝만 4px 둥근 가로 막대."""
    r = min(4.0, w / 2, h / 2)
    if w <= 0:
        return ""
    path = (
        f"M{x:.1f},{y:.1f} h{w - r:.1f} a{r},{r} 0 0 1 {r},{r} v{h - 2 * r:.1f} "
        f"a{r},{r} 0 0 1 -{r},{r} h-{w - r:.1f} z"
    )
    return f'<path d="{path}" fill="{color}"><title>{escape(tip)}</title></path>'


def _goal_label(key: str) -> str:
    text = target_text(key)
    return text if TARGETS.get(key) is None else f"목표 {text}"


def kpi_svg(report: Mapping[str, Any] | None) -> str:
    """K1~K5 숫자 카드 3 × 2."""
    cols, tile_w, tile_h, gap, pad = 3, 300, 150, 16, 24
    width = pad * 2 + cols * tile_w + (cols - 1) * gap
    rows = math.ceil(len(KPIS) / cols)
    height = pad * 2 + 36 + rows * tile_h + (rows - 1) * gap
    body = [_text(pad, pad + 20, "핵심 지표 K1~K5", 20, "primary", weight=600)]
    for i, (key, title, desc, unit) in enumerate(KPIS):
        x = pad + (i % cols) * (tile_w + gap)
        y = pad + 36 + (i // cols) * (tile_h + gap)
        state = verdict(key, report)
        body += [
            f'<rect x="{x}" y="{y}" width="{tile_w}" height="{tile_h}" rx="8" fill="#ffffff" '
            f'stroke="{BORDER}"/>',
            _text(x + 16, y + 28, title, 15, "secondary", weight=600),
            _text(x + 16, y + 76, fmt((report or {}).get(key), unit), 36, "primary", weight=600),
            _text(x + 16, y + 104, desc, 12, "muted"),
            _text(x + 16, y + 132, _goal_label(key), 13, "secondary"),
        ]
        if state in ("pass", "fail"):
            cx = x + tile_w - 92
            body.append(f'<circle cx="{cx}" cy="{y + 127}" r="6" fill="{STATUS[state]}"/>')
            body.append(_text(cx + 12, y + 132, VERDICT_TEXT[state], 13, "secondary"))
        elif state == "pending":  # 목표 미정은 왼쪽 글자로 이미 보인다
            body.append(_text(x + tile_w - 16, y + 132, VERDICT_TEXT[state], 13, "muted", "end"))
    return _svg(width, height, "핵심 지표 K1~K5", body)


def bar_svg(
    title: str,
    items: Sequence[tuple[str, float | None]],
    target: float | None = None,
    note: str = "",
) -> str:
    """한 지표 비율(0~1)을 그룹별 가로 막대로. 값이 없으면 '평가 후 채움'."""
    label_w, plot_w, pad, row_h, bar_h = 150, 560, 24, 34, 20
    width = pad * 2 + label_w + plot_w + 70
    top = pad + (66 if note else 44)  # 부제가 있으면 눈금선과 겹치지 않게 내린다
    height = top + len(items) * row_h + 40
    x0 = pad + label_w
    body = [_text(pad, pad + 20, title, 20, "primary", weight=600)]
    if note:
        body.append(_text(pad, pad + 40, note, 12, "muted"))
    for tick in (0, 0.25, 0.5, 0.75, 1.0):  # 눈금선 (가장 뒤)
        x = x0 + tick * plot_w
        color = AXIS if tick == 0 else GRID
        body.append(
            f'<line x1="{x:.1f}" y1="{top - 6}" x2="{x:.1f}" '
            f'y2="{top + len(items) * row_h}" stroke="{color}" stroke-width="1"/>'
        )
        body.append(_text(x, top + len(items) * row_h + 18, f"{tick:.0%}", 11, "muted", "middle"))
    has_data = any(v is not None for _, v in items)
    for i, (label, value) in enumerate(items):
        y = top + i * row_h + (row_h - bar_h) / 2
        body.append(_text(x0 - 10, y + bar_h - 5, label, 13, "secondary", "end"))
        if value is None:
            continue
        w = max(value, 0) * plot_w
        body.append(_bar(x0, y, w, bar_h, SERIES[0], f"{label}: {fmt(value, '%')}"))
        body.append(_text(x0 + w + 6, y + bar_h - 5, fmt(value, "%"), 12, "secondary"))
    if target is not None:
        x = x0 + target * plot_w
        body.append(
            f'<line x1="{x:.1f}" y1="{top - 10}" x2="{x:.1f}" '
            f'y2="{top + len(items) * row_h}" stroke="{INK["secondary"]}" '
            f'stroke-width="1.5" stroke-dasharray="4 3"/>'
        )
        body.append(_text(x, top - 14, f"목표 {fmt(target, '%')}", 11, "secondary", "middle"))
    if not has_data:
        body.append(
            _text(
                x0 + plot_w / 2, top + len(items) * row_h / 2, "평가 후 채움", 16, "muted", "middle"
            )
        )
    return _svg(width, height, title, body)


def demo_svg(demo: Mapping[str, Mapping[str, Any]] | None) -> str:
    """시연 앞/뒤 절반을 지표마다 두 막대로 (파랑 = 앞, 주황 = 뒤)."""
    label_w, plot_w, pad, group_h, bar_h, gap = 130, 560, 24, 58, 18, 2
    width = pad * 2 + label_w + plot_w + 70
    top = pad + 64
    height = top + len(DEMO_METRICS) * group_h + 40
    x0 = pad + label_w
    halves = (("first_half", "앞 절반"), ("second_half", "뒤 절반"))
    body = [_text(pad, pad + 20, "시연: 사례가 쌓이며 좋아지는가", 20, "primary", weight=600)]
    for j, (_, name) in enumerate(halves):  # 범례 (계열 2개 → 항상)
        lx = pad + j * 110
        body.append(
            f'<rect x="{lx}" y="{pad + 34}" width="12" height="12" rx="2" fill="{SERIES[j]}"/>'
        )
        body.append(_text(lx + 18, pad + 45, name, 13, "secondary"))
    for tick in (0, 0.25, 0.5, 0.75, 1.0):
        x = x0 + tick * plot_w
        body.append(
            f'<line x1="{x:.1f}" y1="{top - 6}" x2="{x:.1f}" '
            f'y2="{top + len(DEMO_METRICS) * group_h}" '
            f'stroke="{AXIS if tick == 0 else GRID}" stroke-width="1"/>'
        )
        body.append(
            _text(x, top + len(DEMO_METRICS) * group_h + 18, f"{tick:.0%}", 11, "muted", "middle")
        )
    has_data = False
    for i, (key, title) in enumerate(DEMO_METRICS):
        gy = top + i * group_h + (group_h - 2 * bar_h - gap) / 2
        body.append(_text(x0 - 10, gy + bar_h + 5, title, 13, "secondary", "end"))
        for j, (half, name) in enumerate(halves):
            value = (demo or {}).get(half, {}).get(key)
            if value is None:
                continue
            has_data = True
            y = gy + j * (bar_h + gap)
            w = max(value, 0) * plot_w
            body.append(_bar(x0, y, w, bar_h, SERIES[j], f"{title} · {name}: {fmt(value, '%')}"))
            body.append(_text(x0 + w + 6, y + bar_h - 4, fmt(value, "%"), 12, "secondary"))
    if not has_data:
        body.append(
            _text(
                x0 + plot_w / 2,
                top + len(DEMO_METRICS) * group_h / 2,
                "평가 후 채움",
                16,
                "muted",
                "middle",
            )
        )
    return _svg(width, height, "시연: 앞 절반 vs 뒤 절반", body)


# --- 묶기 -------------------------------------------------------------------------------------


def _metric_items(
    groups: Mapping[str, Mapping[str, Any]] | None,
    key: str,
    names: Sequence[str],
    ko: Mapping[str, str] | None = None,
) -> list[tuple[str, float | None]]:
    groups = groups or {}
    keys = (
        list(names)
        if not groups
        else [g for g in names if g in groups] + [g for g in groups if g not in names]
    )
    return [((ko or {}).get(g, str(g)), groups.get(g, {}).get(key)) for g in keys]


def render(
    result: Mapping[str, Any] | None,
    demo_result: Mapping[str, Any] | None = None,
    out_dir: Path = OUT_DIR,
) -> list[Path]:
    """결과(없으면 빈 틀) → docs/results/ 의 results.md + SVG. 만든 파일 목록."""
    report = (result or {}).get("report")
    by_category = (result or {}).get("by_category")
    by_language = (result or {}).get("by_language")
    demo = (demo_result or result or {}).get("demo")
    categories = [c.value for c in Category]
    languages = sorted(by_language) if by_language else ["en", "es", "fr", "de", "ja", "zh"]
    note = (
        f"{result['split']} · 처리 {report['processed']}/{report['gold_count']}건 · "
        f"{result['run_id']}"
        if result and report
        else "평가 전 — 숫자는 run_eval 결과로 채운다"
    )
    files = {
        "kpi.svg": kpi_svg(report),
        "category_k3.svg": bar_svg(
            "유형별 근거 일치율 (K3)",
            _metric_items(by_category, "K3_evidence_top3", categories, CATEGORY_KO),
            note=note,
        ),
        "category_accuracy.svg": bar_svg(
            "유형별 분류 정확도",
            _metric_items(by_category, "category_accuracy", categories, CATEGORY_KO),
            note=note,
        ),
        "language_k3.svg": bar_svg(
            "언어별 근거 일치율 (K3)",
            _metric_items(by_language, "K3_evidence_top3", languages),
            note=note,
        ),
        "demo.svg": demo_svg(demo),
    }
    markdown = "\n".join(
        [
            "# 최종 시험 결과 (CSA-51)",
            "",
            f"> {note}",
            ">",
            "> 이 파일과 그래프는 `python -m cs_agent.evaluation.presentation <결과 JSON>`"
            " 이 만든다.",
            "",
            "## 핵심 지표 K1~K5",
            "",
            "![핵심 지표](kpi.svg)",
            "",
            kpi_table(report),
            "",
            "## 유형별",
            "",
            "![유형별 근거 일치율](category_k3.svg)",
            "",
            "![유형별 분류 정확도](category_accuracy.svg)",
            "",
            group_table(by_category, "유형", categories, CATEGORY_KO),
            "",
            "## 언어별",
            "",
            "![언어별 근거 일치율](language_k3.svg)",
            "",
            group_table(by_language, "언어", languages),
            "",
            "## 틀린 건 — 담당 카드별",
            "",
            owner_table((result or {}).get("mistakes")),
            "",
            "## 시연: 사례가 쌓이며 좋아지는가 (앞 절반 vs 뒤 절반)",
            "",
            "![시연 비교](demo.svg)",
            "",
            demo_table(demo),
            "",
        ]
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for name, content in {**files, "results.md": markdown}.items():
        path = out_dir / name
        path.write_text(content + ("" if content.endswith("\n") else "\n"), encoding="utf-8")
        written.append(path)
    return written


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="발표용 결과 표·그래프 (CSA-51)")
    parser.add_argument("result", nargs="?", type=Path, help="run_eval 결과 JSON (없으면 빈 틀)")
    parser.add_argument("--demo-result", type=Path, help="--demo 로 돌린 결과 JSON (시연 비교)")
    parser.add_argument("--out", type=Path, default=OUT_DIR)
    args = parser.parse_args(argv)

    result = json.loads(args.result.read_text()) if args.result else None
    demo = json.loads(args.demo_result.read_text()) if args.demo_result else None
    for path in render(result, demo, args.out):
        print(path.relative_to(REPO_ROOT) if path.is_relative_to(REPO_ROOT) else path)


if __name__ == "__main__":
    main()
