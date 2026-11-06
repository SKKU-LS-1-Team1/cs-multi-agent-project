"""챗봇 실전 점검(evaluation/chat_smoke.py). 실제 LLM 없이 시나리오 파일과 판정만 확인한다.

실제 서버 점검은 .github/workflows/chat-smoke.yml 이 돌린다.
"""

import json

import pytest

from cs_agent.chatbot.agent import DECLINE_ANSWER
from cs_agent.evaluation.chat_smoke import SCENARIOS, check

ALLOWED_KEYS = {"name", "turns", "handoff", "nav_product", "nav_tab", "candidates", "answer_has"}

# 운영에서 고객이 겪은 문제. 시나리오를 정리하다 지워지지 않게 고정한다.
INCIDENT_TURNS = (
    "UPS 보증기간이랑 정격용량 알려줘",  # 2026-10-23 주제가 바뀐 뒤 E.OC
    "S100 인버터 보증기간이랑 정격 용량 알려주세요",  # 2026-10-23 보증 승인으로 보고 전환
    "E.OC 떴어요",  # 2026-10-23 Gemini 504
    "무정전전원장치에 대해 궁금한 점이 있어요",  # 2026-10-23 질문 전인 말을 전환
    "인터버 종류 뭐있어?",  # 2026-10-30 제품 이름 오타를 전환
)


def scenarios() -> list[dict]:
    return json.loads(SCENARIOS.read_text(encoding="utf-8"))


def reply(**overrides) -> dict:
    base = {
        "handoff": False,
        "answer": "보증 기간은 24개월입니다.",
        "navigation": {"product_code": "INV-LSLV0075-S100", "tab": "faults", "candidates": ["A"]},
    }
    return base | overrides


def test_scenarios_have_valid_shape() -> None:
    items = scenarios()
    names = [s["name"] for s in items]
    assert len(names) == len(set(names))
    for scenario in items:
        assert set(scenario) <= ALLOWED_KEYS, scenario["name"]
        assert scenario["turns"] and all(scenario["turns"]), scenario["name"]
        assert isinstance(scenario["handoff"], bool), scenario["name"]


def test_incident_turns_stay_in_scenarios() -> None:
    turns = {turn for s in scenarios() for turn in s["turns"]}
    assert set(INCIDENT_TURNS) <= turns


def test_decline_expectation_matches_fixed_answer() -> None:
    # 범위 밖 시나리오의 기대 문구가 고정 안내 문장과 어긋나면 운영 점검이 늘 실패한다
    declined = [s for s in scenarios() if "제공되지 않습니다" in s.get("answer_has", [])]
    assert declined
    assert "제공되지 않습니다" in DECLINE_ANSWER["ko"]
    assert all(s["handoff"] is False for s in declined)


def test_check_passes_when_reply_matches() -> None:
    scenario = {
        "handoff": False,
        "nav_product": "INV-LSLV0075-S100",
        "nav_tab": "faults",
        "candidates": ["A"],
        "answer_has": ["24"],
    }
    assert check(scenario, reply()) == []


@pytest.mark.parametrize(
    ("scenario", "expected"),
    [
        ({"handoff": True}, "handoff=False"),
        ({"handoff": False, "nav_product": "X"}, "화면 제품"),
        ({"handoff": False, "nav_tab": "docs"}, "화면 탭"),
        ({"handoff": False, "candidates": ["B"]}, "제품 선택 버튼"),
        ({"handoff": False, "answer_has": ["7.5"]}, "답변에 없음"),
    ],
)
def test_check_reports_each_mismatch(scenario: dict, expected: str) -> None:
    problems = check(scenario, reply())
    assert len(problems) == 1 and expected in problems[0]
