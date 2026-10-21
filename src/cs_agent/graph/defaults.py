# 에이전트 임시 구현 (CSA-21 · 담당 김동규)
#
# 그래프가 처음부터 끝까지 돌도록, 아직 구현되지 않은 에이전트 자리를 최소 동작으로 채운다.
# 담당자가 agents/*.py 를 만들면 graph/builder.py 의 GraphDeps 기본값을 그 함수로 바꾸고
# 여기 함수를 지운다. 함수 모양은 각 agents/*.py 의 "만들 것" 주석과 같다.
#
# | 자리 | 임시 동작 | 실제 구현 |
# |---|---|---|
# | write_info_request | llm.write("info_request") 한 번 | agents/info_request.py (CSA-27) |
from cs_agent.llm.router import LLMRouter


def write_info_request(missing: list[str], language: str, summary: str, llm: LLMRouter) -> str:
    prompt = (
        f"Write a short, polite message in language '{language}' asking the customer for all of "
        f"these items at once: {', '.join(missing)}.\nTheir inquiry: {summary}"
    )
    return llm.write("info_request", prompt)
