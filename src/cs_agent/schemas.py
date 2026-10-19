"""에이전트 사이에서 주고받는 값과 API 입출력 모델."""

from datetime import datetime

from pydantic import BaseModel, Field

from cs_agent.domain import Category, FeedbackReason, ReviewAction, Route, Urgency


class InquiryIn(BaseModel):
    """채널 공통 접수 형식 (① 접수, C-01)."""

    channel: str = "WEB_FORM"  # EMAIL | PARTNER_PORTAL | WEB_FORM | PHONE | CHAT
    customer_id: str | None = None
    customer_tier: str = "STANDARD"  # STANDARD | GOLD | PLATINUM
    country: str | None = None
    language: str = "en"
    subject: str = ""
    body: str
    product_code: str | None = None  # 문의서·챗봇이 미리 채운 값
    category: Category | None = None
    provided_fields: dict[str, str] = Field(default_factory=dict)
    thread_ref: str | None = None  # 메일 스레드 등 후속 문의 연결 키
    received_at: datetime | None = None


class Classification(BaseModel):
    category: Category
    secondary_category: Category | None = None
    confidence: float = 0.0
    model: str = ""


class Extraction(BaseModel):
    product_code: str | None = None  # 못 찾으면 None ("미확인")
    product_family: str | None = None
    error_code: str | None = None
    fw_version: str | None = None
    serial_no: str | None = None
    urgency: Urgency = Urgency.NONE
    language: str = "en"
    provided_info: list[str] = Field(default_factory=list)


class Evidence(BaseModel):
    source: str  # docs | cases
    doc_id: str
    section: str | None = None
    text: str
    score: float = 0.0


class RuleResult(BaseModel):
    priority: str
    priority_rule_id: str
    assigned_dept: str
    routing_rule_id: str
    escalate_to: str | None = None
    required_info: list[str]
    missing_info: list[str]
    missing_blocking: list[str]
    sla_first_response_h: float
    sla_resolution_h: float
    sla_id: str


class Draft(BaseModel):
    text: str
    template: str
    slots: dict[str, str] = Field(default_factory=dict)
    cited: list[str] = Field(default_factory=list)  # doc_id#section
    model: str = ""


class CheckResult(BaseModel):
    name: str
    passed: bool
    reason: str = ""


class ReviewIn(BaseModel):
    """상담원 버튼 입력. 그래프 interrupt 지점에 resume 값으로 들어간다 (CSA-25)."""

    action: ReviewAction
    reviewer: str | None = None
    edited_text: str | None = None
    feedback: str | None = None
    feedback_reason: FeedbackReason | None = None
    escalate_to: str | None = None
    info_items: list[str] | None = None


class TicketOut(BaseModel):
    ticket_id: str
    status: str
    route: Route | None = None
    category: Category | None = None
    product_code: str | None = None
    priority: str | None = None
    assigned_dept: str | None = None
    sla_due_at: datetime | None = None
    draft: Draft | None = None
    info_request: str | None = None
    checks: list[CheckResult] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
