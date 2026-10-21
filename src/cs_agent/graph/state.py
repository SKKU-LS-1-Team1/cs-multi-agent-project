# 그래프 상태 TicketState (CSA-21 · 담당 김동규 · Sprint 1)
#
# 노드는 바꾼 키만 dict 로 돌려준다.
# 모든 판단 필드에 rule_id / confidence / evidence 가 같이 들어가 N-04(추적성)를 채운다.
#
# 참고: analysis/agent-architecture/에이전트_구조_제안.md 7장, 관리자_대시보드_AI기능_구조검토.md
#   4장
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
    # 괄호 = 채우는 노드
    ticket_id: str
    inquiry: InquiryIn  # ① 접수
    classification: Classification | None  # ② 분류, CSA-26
    extraction: Extraction | None  # ③ 추출, CSA-26
    analysis_error: str | None  # ②③ 실패 사유 (AnalysisError) → 분석 대기
    candidates: list[Evidence]  # ④ 1차 검색, CSA-28
    rules: RuleResult | None  # ⑤ 규칙 처리, CSA-22. 분석 실패면 None
    route: str | None  # ⑥ 분기: human | info_request | draft (domain.Route), 분석 대기면 None
    evidence: list[Evidence]  # ⑧ 근거 확정, CSA-28
    draft: Draft | None  # ⑨ 답변 작성, CSA-29·30
    checks: list[CheckResult]  # ⑩ 자동 점검, CSA-31
    retries: int  # 자동 점검 재작성 횟수, 최대 2
    fix_notes: list[str]  # ⑩ 실패 사유 → ⑨ 재작성에 넘김
    info_request: str | None  # ⑦ 추가정보 요청문, CSA-27
    pending: str  # 상담원이 검토할 대상: draft | info_request
    review: ReviewIn | None  # 상담원 버튼 입력, CSA-25
    review_rounds: int  # 상담원 재작성 요청 횟수, 자동 점검과 따로 센다
    followups: int  # 고객 회신(재문의)으로 다시 돈 횟수 (services/tickets.py reply)
    final_reply: str | None
    approved_reply: str | None  # 상담원이 승인·수정 승인한 원문 (번역 실패 시에도 보존)
    translation_error: str | None  # 고객 언어 번역 실패 → ON_HOLD, 재승인으로 재시도
    escalated_to: str | None
    status: str  # domain.TicketStatus
