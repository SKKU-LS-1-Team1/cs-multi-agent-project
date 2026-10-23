# 챗봇 실전 점검 (배포·시연 전에 돌린다)
#
# 실제 서버(POST /api/chat)에 data/eval/chat_smoke.json 의 대화를 보내고, 상담원 전환 여부·
# 화면 이동·답변에 들어가야 할 값을 확인한다. 하나라도 틀리면 종료 코드 1.
#
#   uv run python -m cs_agent.evaluation.chat_smoke http://localhost:8000
#   uv run python -m cs_agent.evaluation.chat_smoke https://luckystar-global-cs.com
#
# 실제 LLM 을 부르므로 한 번에 Gemini 호출이 수십 번 든다 (대화 20개, 동시에 4개씩, 몇 분).
# 운영에서 고객이 겪은 문제는 이 파일에 대화로 더해 둔다 (같은 문제가 다시 나오지 않게).
import argparse
import json
import sys
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

SCENARIOS = Path(__file__).resolve().parents[3] / "data" / "eval" / "chat_smoke.json"
TIMEOUT_S = 240


def _chat(base: str, session: str, message: str) -> dict:
    body = json.dumps({"session_id": session, "message": message}).encode()
    request = urllib.request.Request(
        base.rstrip("/") + "/api/chat", body, {"content-type": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:
        return json.load(response)


def check(scenario: dict, reply: dict) -> list[str]:
    """마지막 응답이 기대와 다른 점 목록 (비었으면 통과)."""
    problems = []
    if reply["handoff"] != scenario["handoff"]:
        problems.append(f"handoff={reply['handoff']} (기대 {scenario['handoff']})")
    nav = reply["navigation"]
    if "nav_product" in scenario and nav["product_code"] != scenario["nav_product"]:
        problems.append(f"화면 제품 {nav['product_code']} (기대 {scenario['nav_product']})")
    if "nav_tab" in scenario and nav["tab"] != scenario["nav_tab"]:
        problems.append(f"화면 탭 {nav['tab']} (기대 {scenario['nav_tab']})")
    missing = [c for c in scenario.get("candidates", []) if c not in nav["candidates"]]
    if missing:
        problems.append(f"제품 선택 버튼에 없음: {missing}")
    absent = [v for v in scenario.get("answer_has", []) if v not in reply["answer"]]
    if absent:
        problems.append(f"답변에 없음: {absent}")
    return problems


def run(base: str, scenario: dict) -> tuple[dict, dict | None, list[str]]:
    session = f"smoke-{uuid.uuid4()}"
    try:
        reply = None
        for message in scenario["turns"]:
            reply = _chat(base, session, message)
    except Exception as e:  # 서버 오류도 실패로 센다
        return scenario, None, [f"요청 실패: {type(e).__name__}: {e}"]
    return scenario, reply, check(scenario, reply)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="챗봇 실전 점검")
    parser.add_argument("base", help="서버 주소, 예: http://localhost:8000")
    parser.add_argument("--scenarios", type=Path, default=SCENARIOS)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args(argv)

    scenarios = json.loads(args.scenarios.read_text(encoding="utf-8"))
    failed = 0
    with ThreadPoolExecutor(args.workers) as pool:
        for scenario, reply, problems in pool.map(lambda s: run(args.base, s), scenarios):
            mark = "통과" if not problems else "실패"
            failed += bool(problems)
            print(f"[{mark}] {scenario['name']}", flush=True)
            if problems:
                print(f"       {'; '.join(problems)}")
                if reply:
                    print(f"       답변: {reply['answer'][:200]!r}")
    print(f"\n{len(scenarios) - failed}/{len(scenarios)} 통과")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
