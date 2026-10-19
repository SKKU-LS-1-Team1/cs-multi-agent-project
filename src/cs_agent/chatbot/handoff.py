"""문의 전환 판단 (CSA-35 기준값 확정 · 담당 박종석).

전환 조건(기획서 5.5): 고객이 해결 안 됨 / 원격 조치 후 같은 증상 재발 / 결정이 필요한 문의 /
근거 문서를 못 찾음(검색 점수 < 기준). 기준값은 시험 문의로 확정한다.
"""

from dataclasses import dataclass

from cs_agent.domain import Category

MIN_RETRIEVAL_SCORE = 0.2  # TODO(CSA-35): 시험 문의로 확정
MAX_REMOTE_RETRIES = 1  # TODO(CSA-35): 원격 조치 재시도 횟수
DECISION_CATEGORIES = {Category.QUOTE, Category.ORDER_LEAD, Category.WARRANTY, Category.RETURN}


@dataclass
class HandoffDecision:
    handoff: bool
    reason: str = ""


def should_handoff(
    category: Category | None,
    best_score: float,
    customer_unresolved: bool = False,
    remote_attempts: int = 0,
) -> HandoffDecision:
    if customer_unresolved:
        return HandoffDecision(True, "고객이 해결되지 않았다고 답했습니다.")
    if category in DECISION_CATEGORIES:
        return HandoffDecision(True, "견적·납기·보증·반품은 담당자 확인이 필요합니다.")
    if remote_attempts > MAX_REMOTE_RETRIES:
        return HandoffDecision(True, "안내한 조치 후에도 같은 증상이 반복됩니다.")
    if best_score < MIN_RETRIEVAL_SCORE:
        return HandoffDecision(True, "공개 문서에서 답을 찾지 못했습니다.")
    return HandoffDecision(False)
