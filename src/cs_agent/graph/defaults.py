# 에이전트 임시 구현 (CSA-21 · 담당 김동규)
#
# 그래프가 처음부터 끝까지 돌도록, 아직 구현되지 않은 에이전트 자리를 최소 동작으로 채운다.
# 담당자가 agents/*.py 를 만들면 graph/builder.py 의 GraphDeps 기본값을 그 함수로 바꾸고
# 여기 함수를 지운다. 함수 모양은 각 agents/*.py 의 "만들 것" 주석과 같다.
#
# | 자리 | 임시 동작 | 실제 구현 |
# |---|---|---|
# | write_draft | llm.write("draft") 한 번 | agents/drafting.py (CSA-29·30) |
# | write_info_request | llm.write("info_request") 한 번 | agents/info_request.py (CSA-27) |
from cs_agent.domain import Category
from cs_agent.llm.router import LLMRouter
from cs_agent.schemas import Draft, Evidence, Extraction


def write_draft(
    category: Category,
    extraction: Extraction,
    evidence: list[Evidence],
    inquiry_text: str,
    llm: LLMRouter,
    fix_notes: list[str] | None = None,
    reviewer_feedback: str | None = None,
) -> Draft:
    lines = [
        "You are a customer support agent. Write a reply to the inquiry below.",
        f"Inquiry category: {category}",
        f"Reply in the customer's language ({extraction.language or 'same as the inquiry'}).",
    ]
    if evidence:
        lines.append("Use only these references:")
        lines += [f"[{e.doc_id}#{e.section}] {e.text}" for e in evidence]
    if fix_notes:
        lines.append("Fix these problems from the last check: " + "; ".join(fix_notes))
    if reviewer_feedback:
        lines.append(f"The agent asked for this change: {reviewer_feedback}")
    lines.append(f"Inquiry:\n{inquiry_text}")
    return Draft(
        text=llm.write("draft", "\n".join(lines)),
        cited=[f"{e.doc_id}#{e.section}" for e in evidence],
        model=llm.writer.name,
    )


def write_info_request(missing: list[str], language: str, summary: str, llm: LLMRouter) -> str:
    prompt = (
        f"Write a short, polite message in language '{language}' asking the customer for all of "
        f"these items at once: {', '.join(missing)}.\nTheir inquiry: {summary}"
    )
    return llm.write("info_request", prompt)
