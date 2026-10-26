# 사례 기반 RAG — 해결 확정 문의를 사례 DB(`cases`)에 저장 (기획서 7.1 · 담당 김동규 ·
#   CSA-15·CSA-25)
#
# services/tickets.py 의 resolve() 가 부른다.
#
# 할 일
# 1. 저장 시점: 승인·발송이 아니라 문의가 '해결(RESOLVED)'로 바뀔 때.
#    - 그대로 승인 / 수정 후 승인 → 저장 (수정본이면 수정본 + 수정 사유)
#    - 전문부서 이관 → 이관 부서가 해결 확정하면 저장
#    - AI 재작성 중간본 · 추가정보 요청 · 반려 → 저장하지 않음
#    SAVE_ON 에 저장 대상 상담원 행동을 정의한다.
# 2. build_case(): 그래프 상태 → 사례 문서 (요약, 제품·유형·에러코드, 원인, 조치, 최종 답변, 근거,
#      수정 사유).
# 3. 개인정보 가리기: 회사명·연락처·시리얼 번호 (mask_pii).
# 4. 저장: PostgreSQL resolution_cases 에 행 + embedding(pgvector) 을 같이 upsert (CSA-24·18).
# 5. 재문의로 다시 열린 문의의 사례는 검색 대상에서 잠시 뺀다.
# 6. 사실 오류(FACT_ERROR)로 고친 건은 원천(기준표·문서)도 고치도록 알림을 남긴다.
#
# 완료 기준
# - 시연: test 문의를 순서대로 처리하며 해결 건을 쌓고, 앞 절반 vs 뒤 절반 무수정 승인율 비교
#     (CSA-15)
#
# 시연 방식 (CSA-15 제안): test 597건을 received_at 순서로 그래프에 넣고, 상담원 대신
#   tickets.final_reply(실제 회신)를 정답으로 쓴다. AI 초안이 실제 회신과 같은 내용이면 approve,
#   다르면 edit_approve(edited_text = 실제 회신). 바로 resolve 해서 사례가 쌓이게 한다.
#   앞 절반 vs 뒤 절반의 approve 비율로 피드백 루프 효과를 보인다 (evaluation/run_eval.py, CSA-50).
#
# 피드백 루프 (해결 → 다음 문의의 근거)
#   resolve() → build_case()(pattern_id) → records.save_case()(resolution_cases + 패턴)
#   → 다음 문의의 retrieval.first_pass/finalize_evidence 가 패턴 DB 로 찾는다 → drafting 이 문장
#   본보기로 쓴다 (값은 docs·기준표). 모델을 다시 학습시키는 것이 아니라 패턴의 해결 건수·대표
#   사례가 늘고, 카탈로그에 없던 원인이면 새 패턴이 생긴다 (agents/case_patterns.py, CSA-28).
#   - 저장 (할 일 4): services/records.py save_case. 사례 글은 임베딩하지 않는다 (패턴 설명만).
#     새 패턴 설명의 임베딩이 실패했으면 records.embed_missing_cases() 가 채운다
#     (main.py 가 case_embed_interval_s 마다, live 일 때).
#   - DB·키 없는 로컬은 case_patterns.MemoryPatternRetriever 가 train 사례 CSV 와 운영 중 해결
#     사례(records.live_cases)를 패턴으로 묶어 찾는다 (main.py 가 with_live_cases 로 붙인다).
#   - 재문의 제외 (할 일 5): records.deactivate_case → active=false (검색은 active 만).
#   - 할 일 6 은 사례에 표시(source_fix_needed)만 한다 (원천을 고치라는 알림은 아직 없다).
#   - 사례 답변은 고객에게 나간 final_reply(고객 언어 번역본, CSA-27·29)다 (tests/test_api.py 고정).
#
# 참고: 기획서 v10 7장·7.1
import re
from collections.abc import Mapping
from typing import Any

from cs_agent.agents.case_patterns import assign_pattern
from cs_agent.domain import FeedbackReason, ReviewAction
from cs_agent.schemas import Evidence

# 해결 확정 때 사례로 남기는 마지막 상담원 행동. 이관 건은 이관 부서가 해결 확정하면 저장한다.
SAVE_ON: set[ReviewAction] = {
    ReviewAction.APPROVE,
    ReviewAction.EDIT_APPROVE,
    ReviewAction.ESCALATE,
}

MASK = "**MASKED**"
_PII_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"), MASK),  # 이메일
    (re.compile(r"\bCOMPANY_\d+_\d+\b"), MASK),  # 데이터의 회사명 토큰
    # 시리얼: "Serial number (nameplate): X", "Serial no: X", "S/N: X"
    (
        re.compile(r"(?i)(serial (?:number(?: \(nameplate\))?|no\.?)\s*[:=]\s*)[^\s,;]+"),
        r"\1" + MASK,
    ),
    (re.compile(r"(?i)\b(S/N|SN)([:#]?\s*)[A-Z0-9][A-Z0-9-]{4,}\b"), r"\1\2" + MASK),
    # 전화번호: + 로 시작하거나 Tel/Phone/Mobile 뒤 (날짜는 건드리지 않는다)
    (re.compile(r"\+\d[\d\s()-]{7,}\d"), MASK),
    (re.compile(r"(?i)\b(tel|phone|mobile)(\.?:?\s*)\(?\d[\d\s()-]{6,}\d"), r"\1\2" + MASK),
]


def mask_pii(text: str) -> str:
    """회사명·연락처·시리얼 번호를 가린다."""
    for pattern, repl in _PII_PATTERNS:
        text = pattern.sub(repl, text)
    return text


def _dump(value: Any) -> dict:
    if value is None:
        return {}
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return dict(value)


def build_case(state: dict) -> dict:
    """그래프 상태 → 사례 문서. text 는 임베딩용, 나머지는 메타데이터."""
    inquiry = _dump(state.get("inquiry"))
    classification = _dump(state.get("classification"))
    extraction = _dump(state.get("extraction"))
    rules = _dump(state.get("rules"))
    draft = _dump(state.get("draft"))
    review = _dump(state.get("review"))
    slots = draft.get("slots") or {}
    original_review = _dump(state.get("approval_review"))
    if original_review and original_review.get("edited_text") == state.get("approved_reply"):
        review = original_review
    resolution = _dump(state.get("resolution"))
    if resolution and (resolution.get("outcome") == "unconfirmed" or resolution.get("superseded")):
        raise ValueError("Unconfirmed or superseded closure is not a verified resolution case")

    final_reply = state.get("final_reply") or ""
    # Legacy evaluation callers without confirmed results keep their existing contract.
    if not resolution:
        final_reply = final_reply or review.get("edited_text") or draft.get("text") or ""

    def masked(value: str) -> str:
        serial = extraction.get("serial_no")
        if serial:
            value = value.replace(serial, MASK)
        return mask_pii(value)

    summary = masked(inquiry.get("subject") or inquiry.get("body", "")[:200])
    cause = (
        resolution.get("cause")
        if resolution
        else slots.get("root_cause") or slots.get("cause") or ""
    )
    action = resolution.get("action") if resolution else slots.get("action") or ""
    cause, action = masked(cause or ""), masked(action or "")
    feedback_reason = review.get("feedback_reason")

    lines = [summary]
    if cause:
        lines.append(f"Cause: {cause}")
    if action:
        lines.append(f"Corrective action: {action}")
    if resolution:
        lines.extend(
            [
                f"Outcome: {resolution['outcome']}",
                f"Confirmed result: {masked(resolution['result'])}",
                f"Verification: {masked(resolution['verification'])}",
            ]
        )
    lines.append(f"Reply: {masked(final_reply)}")

    cited = (
        state["approval_cited"]
        if state.get("approved_reply") and state.get("approval_cited") is not None
        else draft.get("cited") or []
    )
    return {
        "case_id": f"CASE-{state['ticket_id']}",
        "ticket_id": state["ticket_id"],
        "text": "\n".join(lines),
        "summary": summary,
        "product_code": extraction.get("product_code"),
        "product_family": extraction.get("product_family"),
        "category": classification.get("category"),
        "error_code": extraction.get("error_code"),
        "cause": cause,
        "action": action,
        "final_reply": masked(final_reply),
        "cited": list(
            dict.fromkeys(
                [
                    *cited,
                    *(ref["id"] for ref in resolution.get("references", [])),
                ]
            )
        ),
        # 학습: 확정 원인으로 패턴을 정한다 (카탈로그 원인과 같으면 fault_id, 아니면 LIVE-…)
        # 원인 없는 예전 방식 해결(평가 시연)은 문의 요약으로 묶는다
        "pattern_id": assign_pattern(extraction.get("product_family"), cause or summary),
        "resolved_by_dept": state.get("escalated_to") or rules.get("assigned_dept"),
        "review_action": review.get("action"),
        "edited": review.get("action") == ReviewAction.EDIT_APPROVE,
        "feedback": masked(review["feedback"]) if review.get("feedback") else None,
        "feedback_reason": feedback_reason,
        # 할 일 6: 사실 오류로 고친 건은 기준표·문서도 고쳐야 한다
        "source_fix_needed": feedback_reason == FeedbackReason.FACT_ERROR,
        "active": True,  # 할 일 5: 재문의로 다시 열리면 False 로 바꿔 검색에서 뺀다
    }


# 운영 중 해결 사례를 키워드 검색에도 (DB·임베딩 없는 로컬) ---------------------------------------


def case_evidence(case: Mapping[str, Any]) -> Evidence:
    """build_case() 사례 → 검색 결과 Evidence (retrieval.keyword_cases 와 같은 모양)."""
    from cs_agent.agents.retrieval import case_text

    cited = list(case.get("cited") or [])
    return Evidence(
        source="cases",
        doc_id=case["case_id"],
        text=case["text"]
        if "Confirmed result:" in (case.get("text") or "")
        else case_text(
            {
                "case_summary": case.get("summary") or "",
                "root_cause": case.get("cause") or "",
                "action_taken": case.get("action") or "",
            },
            case.get("final_reply") or "",
        ),
        metadata={
            "category": case.get("category") or "",
            "product_code": case.get("product_code") or "",
            "family": case.get("product_family") or "",
            "error_code": case.get("error_code") or "",
            "ticket_id": case.get("ticket_id") or "",
            "reference_doc_id": cited[0].split("#", 1)[0] if cited else "",
        },
    )


def with_live_cases(cases: Any, records: Any) -> Any:
    """로컬 패턴 검색기(DB·임베딩 없음)에 운영 중 해결 사례를 붙인다. pgvector 패턴·None 은 그대로
    (pgvector 패턴 검색은 resolution_cases.pattern_id 로 운영 사례를 바로 센다)."""
    from cs_agent.agents.case_patterns import MemoryPatternRetriever

    if isinstance(cases, MemoryPatternRetriever):
        cases.records = records
    return cases
