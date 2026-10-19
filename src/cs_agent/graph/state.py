"""그래프 상태 (에이전트_구조_제안.md 7장 + 관리자 버튼 필드).

모든 판단 필드에 rule_id / confidence / evidence가 같이 들어가 N-04(추적성)를 채운다.
"""

from typing import TypedDict

from cs_agent.schemas import (
    CheckResult,
    Classification,
    Draft,
    Evidence,
    Extraction,
    InquiryIn,
    ReviewIn,
    RuleResult,
)


class TicketState(TypedDict, total=False):
    ticket_id: str
    inquiry: InquiryIn  # ① 접수
    classification: Classification  # ② 분류
    extraction: Extraction  # ③ 추출
    candidates: list[Evidence]  # ④ 1차 검색
    rules: RuleResult  # ⑤ 규칙 처리
    route: str  # ⑥ 분기: human | info_request | draft
    evidence: list[Evidence]  # ⑧ 근거 확정
    draft: Draft | None  # ⑨ 답변 작성
    checks: list[CheckResult]  # ⑩ 자동 점검
    retries: int  # 자동 점검 재작성 횟수 (최대 2)
    info_request: str | None  # ⑦ 추가정보 요청문 초안
    pending: str  # 상담원 검토 대상: draft | info_request
    review: ReviewIn | None  # 상담원 버튼 입력
    review_rounds: int  # 상담원 재작성 요청 횟수 (자동 점검과 따로 센다)
    final_reply: str | None
    escalated_to: str | None
    status: str
