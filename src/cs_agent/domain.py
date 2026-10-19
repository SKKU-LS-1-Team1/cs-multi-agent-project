"""도메인 상수: 문의 유형, 묶음, 상태, 경로."""

from enum import StrEnum


class Category(StrEnum):
    TECH_SPEC = "TECH_SPEC"
    MANUAL = "MANUAL"
    COMPLIANCE = "COMPLIANCE"
    QUOTE = "QUOTE"
    ORDER_LEAD = "ORDER_LEAD"
    DEFECT = "DEFECT"
    INSTALL = "INSTALL"
    FW_UPDATE = "FW_UPDATE"
    WARRANTY = "WARRANTY"
    RETURN = "RETURN"


class Bundle(StrEnum):
    """기획서 3장 묶음. 답변 작성 모드와 자동 점검 기준이 묶음별로 다르다."""

    INFO = "INFO"  # 정보 안내형: 완성 답변
    DIAGNOSIS = "DIAGNOSIS"  # 기술 진단형: 원인 후보·점검 순서 (단정 금지)
    POLICY = "POLICY"  # 정책 판단형: 판단 재료 (승인·반려 금지)


BUNDLE_OF: dict[Category, Bundle] = {
    Category.TECH_SPEC: Bundle.INFO,
    Category.MANUAL: Bundle.INFO,
    Category.COMPLIANCE: Bundle.INFO,
    Category.QUOTE: Bundle.INFO,
    Category.ORDER_LEAD: Bundle.INFO,
    Category.DEFECT: Bundle.DIAGNOSIS,
    Category.INSTALL: Bundle.DIAGNOSIS,
    Category.FW_UPDATE: Bundle.DIAGNOSIS,
    Category.WARRANTY: Bundle.POLICY,
    Category.RETURN: Bundle.POLICY,
}


class Urgency(StrEnum):
    NONE = "NONE"
    SAFETY = "SAFETY"
    SITE_DOWN = "SITE_DOWN"
    PROD_IMPACT = "PROD_IMPACT"
    COMMISSION = "COMMISSION"
    DEADLINE = "DEADLINE"


class Route(StrEnum):
    HUMAN = "human"  # 안전 건: 초안 없이 사람 큐 (C-08)
    INFO_REQUEST = "info_request"  # 차단성 필수정보 누락 (C-04)
    DRAFT = "draft"  # 정상: 근거 확정 → 답변 작성


class TicketStatus(StrEnum):
    NEW = "NEW"
    HUMAN_QUEUE = "HUMAN_QUEUE"
    WAITING_CUSTOMER = "WAITING_CUSTOMER"  # SLA 시계 정지
    READY_FOR_REVIEW = "READY_FOR_REVIEW"
    ON_HOLD = "ON_HOLD"  # 자동 점검 재시도 초과 (P-03)
    ESCALATED = "ESCALATED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    RESOLVED = "RESOLVED"


class ReviewAction(StrEnum):
    """관리자 화면 버튼 (기획서 6장·7.1, 관리자_대시보드_AI기능_구조검토.md)."""

    APPROVE = "approve"
    EDIT_APPROVE = "edit_approve"
    REWRITE = "rewrite"  # AI 재작성 요청 + 피드백 한 줄
    INFO_REQUEST = "info_request"  # 추가정보 요청문 작성
    ESCALATE = "escalate"  # 전문부서 이관
    REJECT = "reject"


class FeedbackReason(StrEnum):
    """수정 사유 4개 (기획서 7장)."""

    FACT_ERROR = "FACT_ERROR"
    WEAK_EVIDENCE = "WEAK_EVIDENCE"
    TONE = "TONE"
    ROUTING_ERROR = "ROUTING_ERROR"
