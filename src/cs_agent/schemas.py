# 에이전트 사이 · API 입출력 데이터 모델 (CSA-21 · 담당 김동규 · Sprint 1)
#
# 에이전트 담당자들은 이 모양에 맞춰 입출력을 만든다.
# 화면 쪽 타입(frontend/src/api/client.ts)과 이름을 맞춘다. 바꿀 때는 팀에 알린다.
from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field, StringConstraints

from cs_agent.domain import Category, FeedbackReason, ReviewAction, Route, TicketStatus, Urgency

CustomerTier = Literal["STANDARD", "GOLD", "PLATINUM"]


def _utcnow() -> datetime:
    return datetime.now(UTC)


class InquiryIn(BaseModel):
    """① 접수. 5개 채널 공통 형식 (C-01)"""

    channel: str
    customer_id: str | None = None
    customer_tier: CustomerTier = "STANDARD"
    country: str | None = None
    language: str | None = None
    subject: str = ""
    body: str
    product_code: str | None = None  # 문의서·챗봇이 미리 채운 값
    category: Category | None = None  # 고객이 고른 유형
    provided_fields: dict[str, str] = Field(default_factory=dict)
    thread_ref: str | None = None  # 메일 스레드 등 후속 문의 연결 키
    received_at: datetime = Field(default_factory=_utcnow)


class Classification(BaseModel):
    """② 분류"""

    category: Category
    secondary_category: Category | None = None
    confidence: float = 0.0
    model: str = ""


class Extraction(BaseModel):
    """③ 추출"""

    product_code: str | None = None  # None = 미확인
    product_family: str | None = None
    error_code: str | None = None
    fw_version: str | None = None
    serial_no: str | None = None
    urgency: Urgency = Urgency.NONE
    language: str | None = None
    provided_info: list[str] = Field(default_factory=list)  # required_info.csv 의 항목 이름
    field_values: dict[str, str] = Field(default_factory=dict)  # 확인된 항목의 실제 값
    field_evidence: dict[str, str] = Field(default_factory=dict)
    field_sources: dict[str, str] = Field(default_factory=dict)
    unconfirmed_fields: dict[str, str] = Field(default_factory=dict)
    unconfirmed_evidence: dict[str, str] = Field(default_factory=dict)
    field_candidates: dict[str, list[dict[str, str]]] = Field(default_factory=dict)
    issues: list[str] = Field(default_factory=list)
    assessed_urgency: Urgency | None = None
    safety_review_required: bool = False
    # RETURN 일 때만: 불량 반품(DOA·품질)이면 True, 오배송·주문 착오·잉여면 False, 모르면 None.
    # False 면 RT-ALL-RETURN-NON_DEFECT(SCM) 로 보낸다.
    return_defect: bool | None = None


class Evidence(BaseModel):
    """④⑧ 검색 근거"""

    source: Literal["docs", "cases", "specialist"]
    doc_id: str
    section: str | None = None
    text: str
    score: float = 0.0
    # 제품 거르기·유형별 재정렬용 (CSA-28): doc_type·product_code·family·title, 사례는 category 등
    metadata: dict[str, str] = Field(default_factory=dict)


class RuleResult(BaseModel):
    """⑤ 규칙 처리"""

    priority: str
    priority_rule_id: str
    assigned_dept: str
    routing_rule_id: str
    escalate_to: str | None = None
    required_info: list[str] = Field(default_factory=list)
    missing_info: list[str] = Field(default_factory=list)
    missing_blocking: list[str] = Field(default_factory=list)
    sla_first_response_h: float
    sla_resolution_h: float
    sla_id: str


class Draft(BaseModel):
    """⑨ 답변"""

    text: str
    template: str = ""
    slots: dict[str, str] = Field(default_factory=dict)
    cited: list[str] = Field(default_factory=list)  # "doc_id#section"
    model: str = ""


class CheckResult(BaseModel):
    """⑩ 자동 점검"""

    name: str
    passed: bool
    reason: str = ""


class EscalationRequest(BaseModel):
    """CSA-55: 상담원이 검토할 한국어 이관 요청서. 생성 자체는 이관이 아니다."""

    to_dept: str
    reason: str
    summary: str
    fields: dict[str, str]
    cited: list[str]
    text: str
    model: str = ""


class EscalationRequestIn(BaseModel):
    to_dept: str | None = None  # 생략하면 기존 규칙의 escalate_to


NonblankText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=20000)
]
StaffName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
AttachmentName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)
]


class SpecialistRequestIn(BaseModel):
    """CSA-62: 담당자가 확인한 검토 요청. 외부 메일 발송 자체를 의미하지 않는다."""

    request_id: UUID
    to_dept: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=32)]
    text: NonblankText
    requested_by: StaffName
    channel: Annotated[str, StringConstraints(strip_whitespace=True, max_length=64)] = ""
    attachment_names: list[AttachmentName] = Field(default_factory=list, max_length=20)


class SpecialistReplyIn(BaseModel):
    reply_id: UUID
    text: NonblankText
    author: StaffName


class SpecialistReply(SpecialistReplyIn):
    created_at: datetime


class SpecialistRequest(SpecialistRequestIn):
    created_at: datetime
    reply: SpecialistReply | None = None


class ResolutionReference(BaseModel):
    id: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    label: Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)] = ""
    kind: Annotated[str, StringConstraints(strip_whitespace=True, max_length=32)] = ""


class ResolveIn(BaseModel):
    """담당자가 확인한 최종 처리 결과. unconfirmed는 종결만 하고 사례로 학습하지 않는다."""

    outcome: Literal["resolved", "provided", "unconfirmed"]
    cause: NonblankText
    action: NonblankText
    result: NonblankText
    verification: NonblankText
    confirmed_by: StaffName
    references: list[ResolutionReference] = Field(default_factory=list, max_length=50)


class Resolution(ResolveIn):
    confirmed_at: datetime
    superseded: bool = False


class CustomerMessage(BaseModel):
    message_id: str
    kind: Literal["initial", "reply"]
    body: str
    subject: str = ""
    received_at: datetime
    language: str | None = None
    provided_fields: dict[str, str] = Field(default_factory=dict)
    category: Category | None = None
    product_code: str | None = None


class InformationFieldReview(BaseModel):
    status: Literal["missing", "unusable", "confirmed"]
    value: Annotated[str, StringConstraints(strip_whitespace=True, max_length=20000)] | None = None
    evidence: Annotated[str, StringConstraints(strip_whitespace=True, max_length=10000)] = ""


class InformationReviewIn(BaseModel):
    expected_reviewed_at: datetime | None = None
    reply_id: str
    customer_revision: int = Field(ge=0)
    reviewer: StaffName
    fields: dict[str, InformationFieldReview] = Field(min_length=1, max_length=50)


class InformationReview(InformationReviewIn):
    checked_at: datetime


class ManualReplyIn(BaseModel):
    text: str = Field(min_length=1, max_length=30000)
    reviewer: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    expected_customer_revision: int = Field(ge=0)
    expected_specialist_revision: int = Field(ge=0)
    expected_information_reviewed_at: datetime | None = None


class ReplyPreviewIn(BaseModel):
    text: str = Field(min_length=1, max_length=30000)


class ReviewIn(BaseModel):
    """상담원 버튼 입력. 그래프 resume 값"""

    action: ReviewAction
    reply_preview_id: str | None = None
    acknowledged_failures: bool = False
    expected_specialist_revision: int | None = Field(default=None, ge=0)
    expected_customer_revision: int | None = Field(default=None, ge=0)
    expected_information_reviewed_at: datetime | None = None
    reviewer: str = ""
    edited_text: str | None = None
    feedback: str | None = None  # 한 줄
    feedback_reason: FeedbackReason | None = None
    escalate_to: str | None = None
    info_items: list[str] = Field(default_factory=list)  # 요청할 항목


class AssignIn(BaseModel):
    """담당자 재배정 입력 (CSA-53). 같은 부서 담당자만"""

    assignee: str  # data/ref/agents.csv agent_id
    reason: str = ""  # 예: "SLA 75% 경고 — 부재"
    by: str = ""  # 넘긴 사람 (상담원·관리자)


class TicketOut(BaseModel):
    """API 응답"""

    ticket_id: str
    inquiry: InquiryIn | None = (
        None  # 고객 문의 원문 (회신이 오면 이어 붙인 본문). 관리자 화면 표시용
    )
    body_ko: str | None = None
    status: TicketStatus
    manual_reply: bool = False
    processing_history: list[dict] = Field(default_factory=list)
    assignment_history: list[dict] = Field(default_factory=list)
    route: Route | None = None
    category: Category | None = None
    product_code: str | None = None
    priority: str | None = None
    assigned_dept: str | None = None  # 이관됐으면 이관 부서
    assignee: str | None = None  # 담당 상담원 agent_id (CSA-53). 없으면 부서 큐
    sla_due_at: datetime | None = None
    draft: Draft | None = None
    info_request: str | None = None
    escalation_request: EscalationRequest | None = None
    approval_cited: list[str] | None = None
    approval_text: str | None = None
    approval_error: str | None = None
    customer_qc: dict | None = None
    approved_reply: str | None = None
    final_reply: str | None = None
    final_reply_language: str | None = None
    translation_error: str | None = None
    checks: list[CheckResult] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    specialist_requests: list[SpecialistRequest] = Field(default_factory=list)
    specialist_revision: int = 0
    draft_specialist_revision: int = 0
    resolution: Resolution | None = None
    classification: Classification | None = None
    extraction: Extraction | None = None
    rules: RuleResult | None = None
    field_labels: dict[str, str] = Field(default_factory=dict)
    customer_messages: list[CustomerMessage] = Field(default_factory=list)
    customer_revision: int = 0
    draft_customer_revision: int = 0
    draft_information_reviewed_at: datetime | None = None
    information_review: InformationReview | None = None
    information_reviews: list[InformationReview] = Field(default_factory=list)
