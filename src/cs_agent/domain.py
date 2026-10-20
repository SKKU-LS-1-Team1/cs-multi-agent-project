# 도메인 상수 (CSA-21 · 담당 김동규 · Sprint 1) — 팀 전체가 같이 쓰는 값. 바꿀 때는 팀에 알린다.
#
# 값은 tickets 데이터의 코드 그대로 쓴다.
from enum import StrEnum


class Category(StrEnum):
    """문의 유형 10개 (tickets.category_code)"""

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
    """기획서 3장 묶음"""

    INFO = "INFO"  # 정보 안내형
    DIAGNOSIS = "DIAGNOSIS"  # 기술 진단형
    POLICY = "POLICY"  # 정책 판단형


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
    """tickets.urgency_flag"""

    NONE = "NONE"
    SAFETY = "SAFETY"
    SITE_DOWN = "SITE_DOWN"
    PROD_IMPACT = "PROD_IMPACT"
    COMMISSION = "COMMISSION"
    DEADLINE = "DEADLINE"


class Route(StrEnum):
    """⑥ 분기"""

    HUMAN = "human"  # 안전 건 사람 큐
    INFO_REQUEST = "info_request"  # 차단성 누락
    DRAFT = "draft"  # 정상


class TicketStatus(StrEnum):
    NEW = "NEW"
    ANALYSIS_PENDING = "ANALYSIS_PENDING"  # 분류·추출 실패, 자동 재시도 대기
    HUMAN_QUEUE = "HUMAN_QUEUE"
    WAITING_CUSTOMER = "WAITING_CUSTOMER"  # SLA 정지
    READY_FOR_REVIEW = "READY_FOR_REVIEW"
    ON_HOLD = "ON_HOLD"  # 자동 점검 실패 보류
    ESCALATED = "ESCALATED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    RESOLVED = "RESOLVED"


class ReviewAction(StrEnum):
    """관리자 화면 버튼"""

    APPROVE = "approve"
    EDIT_APPROVE = "edit_approve"
    REWRITE = "rewrite"  # AI 재작성
    INFO_REQUEST = "info_request"
    ESCALATE = "escalate"  # 전문부서 이관
    REJECT = "reject"


class FeedbackReason(StrEnum):
    """기획서 7장 수정 사유"""

    FACT_ERROR = "FACT_ERROR"
    WEAK_EVIDENCE = "WEAK_EVIDENCE"
    TONE = "TONE"
    ROUTING_ERROR = "ROUTING_ERROR"
