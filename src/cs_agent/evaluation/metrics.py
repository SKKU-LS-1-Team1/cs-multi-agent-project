"""KPI 계산 (CSA-49 기준선 측정 · 담당 김동규).

K1 처리 지연 p95 · K2 무수정 승인 가능률(정보 안내형) · K3 근거 일치율(doc_id+section) ·
K4 부서·우선순위 일치율 · K5 필수정보 누락 탐지율. 정의와 목표치는 KPI_설정안.md를 따른다.
"""

from collections.abc import Sequence


def accuracy(pred: Sequence, gold: Sequence) -> float:
    pairs = list(zip(pred, gold, strict=True))
    return sum(p == g for p, g in pairs) / len(pairs) if pairs else 0.0


def p95(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(round(0.95 * (len(ordered) - 1))))]


def recall(pred_sets: Sequence[set], gold_sets: Sequence[set]) -> float:
    hit = sum(len(p & g) for p, g in zip(pred_sets, gold_sets, strict=True))
    total = sum(len(g) for g in gold_sets)
    return hit / total if total else 1.0
