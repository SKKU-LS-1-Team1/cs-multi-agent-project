# 그래프 상태 TicketState (CSA-21 · 담당 김동규 · Sprint 1)
#
# 노드는 바꾼 키만 dict 로 돌려준다.
# 모든 판단 필드에 rule_id / confidence / evidence 가 같이 들어가 N-04(추적성)를 채운다.
#
# 참고: analysis/agent-architecture/에이전트_구조_제안.md 7장, 관리자_대시보드_AI기능_구조검토.md
#   4장
from typing import TypedDict

from cs_agent.agents.translation import TranslationPart
from cs_agent.schemas import (
    CheckResult,
    Classification,
    Draft,
    EscalationRequest,
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
    customer_messages: list[dict]  # 최초 문의와 회신 원문·선택값, 시간순
    customer_revision: int  # 새 고객 회신마다 증가
    draft_customer_revision: int  # 현재 초안이 반영한 고객 회신 버전
    draft_information_reviewed_at: str | None  # 현재 초안이 반영한 담당자 정보 확인
    information_review: dict | None
    information_reviews: list[dict]
    information_review_refresh: bool  # 담당자 확인으로 검색·근거를 다시 구성할 때
    manual_reply: bool  # 담당자가 사람 검토 문의에 직접 작성한 답변
    processing_history: list[dict]  # 발송·완료·반려 이력, 고객 회신 시에도 보존
    progress_notices: list[dict]  # 진행 안내 영어 초안·담당자 승인·고객 언어 최종 문구, 발송 없음
    body_ko: str | None  # 상담원 표시용. 원문 분석에는 사용하지 않는다 (CSA-57)
    translation_parts: list[TranslationPart]  # 회신별 원문·번역 성공 구간 (체크포인트)
    translation_job: str | None  # 배경 번역 작업 id (intake 가 시작, ready·hold 등이 받음)
    classification: Classification | None  # ② 분류, CSA-26
    extraction: Extraction | None  # ③ 추출, CSA-26
    analysis_error: str | None  # ②③ 실패 사유 (AnalysisError) → 분석 대기
    candidates: list[Evidence]  # ④ 1차 검색, CSA-28
    rules: RuleResult | None  # ⑤ 규칙 처리, CSA-22. 분석 실패면 None
    route: str | None  # ⑥ 분기: human | info_request | draft (domain.Route), 분석 대기면 None
    evidence: list[Evidence]  # ⑧ 근거 확정, CSA-28
    draft: Draft | None  # ⑨ 답변 작성, CSA-29·30
    drafting_error: str | None  # ⑨ 입력 부족·호출/출력 오류 → 기존 보류·검토 흐름
    checks: list[CheckResult]  # ⑩ 자동 점검, CSA-31
    retries: int  # 자동 점검 재작성 횟수, 최대 2
    fix_notes: list[str]  # ⑩ 실패 사유 → ⑨ 재작성에 넘김
    info_request: str | None  # ⑦ 추가정보 요청문, CSA-27
    escalation_request: EscalationRequest | None  # CSA-55: 검토 전 생성, 회신 시 무효화
    specialist_requests: list[dict]  # CSA-62 요청·회신 기록 (서비스가 갱신)
    specialist_replies: list[dict]  # 작성·검증에 사용하는 현재 문의 회신
    specialist_revision: int  # 요청·회신 갱신 버전
    draft_specialist_revision: int  # 현재 초안이 반영한 전문부서 버전
    pending: str  # 상담원이 검토할 대상: draft | info_request
    review: ReviewIn | None  # 상담원 버튼 입력, CSA-25
    review_rounds: int  # 상담원 재작성 요청 횟수, 자동 점검과 따로 센다
    followups: int  # 고객 회신(재문의)으로 다시 돈 횟수 (services/tickets.py reply)
    resolution: dict | None  # 담당자가 확인한 완료 결과; 재문의 시 superseded
    resolution_case_saved: bool  # 완료 저장 재시도의 중복 임베딩 방지
    approval_review: dict | None  # 최종 승인 후보를 만든 수정본·피드백
    approval_cited: list[str] | None  # 최종 승인 후보 본문의 실제 인용
    reply_preview: dict | None  # 명시적으로 변환해 확인한 발송용 문구
    approval_text: str | None  # 최종 점검 실패 시 담당자 수정본 보존
    customer_qc: dict | None  # 최종 고객 문구 QC; 체크포인트에 저장
    approval_error: str | None
    approval_checks_key: str | None  # 최종 점검한 본문·근거의 지문
    final_reply: str | None
    approved_reply: str | None  # 상담원이 승인·수정 승인한 원문 (번역 실패 시에도 보존)
    translation_error: str | None  # 고객 언어 번역 실패 → ON_HOLD, 재승인으로 재시도
    escalated_to: str | None
    status: str  # domain.TicketStatus
