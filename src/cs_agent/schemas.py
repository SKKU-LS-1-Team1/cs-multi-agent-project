# 에이전트 사이 · API 입출력 데이터 모델 (CSA-21 · 담당 김동규 · Sprint 1)
#
# 에이전트 담당자들은 이 모양에 맞춰 입출력을 만든다.
# 화면 쪽 타입(frontend/src/api/client.ts)과 이름을 맞춘다. 바꿀 때는 팀에 알린다.
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field

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
    # RETURN 일 때만: 불량 반품(DOA·품질)이면 True, 오배송·주문 착오·잉여면 False, 모르면 None.
    # False 면 RT-ALL-RETURN-NON_DEFECT(SCM) 로 보낸다.
    return_defect: bool | None = None


class Evidence(BaseModel):
    """④⑧ 검색 근거"""

    source: Literal["docs", "cases"]
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


class ReviewIn(BaseModel):
    """상담원 버튼 입력. 그래프 resume 값"""

    action: ReviewAction
    reviewer: str = ""
    edited_text: str | None = None
    feedback: str | None = None  # 한 줄
    feedback_reason: FeedbackReason | None = None
    escalate_to: str | None = None
    info_items: list[str] = Field(default_factory=list)  # 요청할 항목


class TicketOut(BaseModel):
    """API 응답"""

    ticket_id: str
    status: TicketStatus
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
