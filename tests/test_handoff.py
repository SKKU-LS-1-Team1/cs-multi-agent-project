import pytest

from cs_agent.chatbot.handoff import (
    MAX_REMOTE_RETRIES,
    MIN_RETRIEVAL_SCORE,
    HandoffDecision,
    should_handoff,
)
from cs_agent.domain import Category

GOOD = 0.82  # valid 중앙값 근처


def test_thresholds_are_decided() -> None:
    assert MIN_RETRIEVAL_SCORE == 0.70
    assert MAX_REMOTE_RETRIES == 2


def test_answerable_question_stays_in_chat() -> None:
    assert should_handoff(Category.TECH_SPEC, GOOD) == HandoffDecision(handoff=False)


def test_customer_unresolved_wins_over_everything() -> None:
    decision = should_handoff(Category.TECH_SPEC, GOOD, customer_unresolved=True)

    assert decision.handoff and decision.code == "customer_unresolved"
    assert decision.reason


def test_remote_retries_only_for_diagnosis() -> None:
    once = should_handoff(Category.DEFECT, GOOD, remote_attempts=1)
    twice = should_handoff(Category.DEFECT, GOOD, remote_attempts=2)
    spec = should_handoff(Category.TECH_SPEC, GOOD, remote_attempts=5)

    assert not once.handoff
    assert (twice.handoff, twice.code) == (True, "remote_retries")
    assert not spec.handoff


@pytest.mark.parametrize(
    "category", [Category.QUOTE, Category.ORDER_LEAD, Category.WARRANTY, Category.RETURN]
)
def test_decision_categories_hand_off(category: Category) -> None:
    decision = should_handoff(category, GOOD)

    assert decision.handoff
    assert decision.code == f"decision_{category.value.lower()}"
    assert decision.reason


def test_low_score_hands_off_and_order_is_kept() -> None:
    assert should_handoff(None, 0.648).code == "no_evidence"  # 범위 밖 질문 최고점
    assert should_handoff(Category.MANUAL, 0.0).code == "no_evidence"  # 근거 없음
    assert not should_handoff(Category.MANUAL, 0.70).handoff
    # 결정 유형은 점수가 낮아도 '결정 필요'가 먼저
    assert should_handoff(Category.ORDER_LEAD, 0.60).code == "decision_order_lead"
