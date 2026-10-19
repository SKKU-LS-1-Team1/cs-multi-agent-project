"""사례 기반 RAG: 해결 확정된 문의를 사례 DB(`cases`)에 저장한다 (기획서 7.1 · 담당 김동규).

저장 시점은 승인·발송이 아니라 '해결' 상태로 바뀔 때. 재작성 중간본·추가정보 요청·반려는
저장하지 않는다. 회사명·연락처·시리얼은 가린다. 시험·검증 문의에 연결된 사례는 처음 적재에서 뺀다.
"""

import re

from cs_agent.domain import ReviewAction

SAVE_ON = {ReviewAction.APPROVE, ReviewAction.EDIT_APPROVE, ReviewAction.ESCALATE}

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
_SERIAL_RE = re.compile(r"\bS/?N[:\s#=]*[A-Z0-9\-]{6,}\b", re.IGNORECASE)


def mask_pii(text: str) -> str:
    return _SERIAL_RE.sub("S/N ***", _EMAIL_RE.sub("***@***", text))


def build_case(state: dict) -> dict:
    """TicketState → 사례 문서. TODO(CSA-28): ChromaDB `cases` 컬렉션에 upsert."""
    draft = state.get("final_reply") or (state["draft"].text if state.get("draft") else "")
    extraction = state["extraction"]
    return {
        "ticket_id": state["ticket_id"],
        "category": state["classification"].category.value,
        "product_code": extraction.product_code,
        "error_code": extraction.error_code,
        "summary": mask_pii(state["inquiry"].body[:500]),
        "final_reply": mask_pii(draft),
        "feedback_reason": state.get("feedback_reason"),
    }
