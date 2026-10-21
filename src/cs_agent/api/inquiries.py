# 고객용 문의 API (CSA-61 · CSA-46 · 담당 김동규) — 고객 화면 문의하기·내 문의 내역 (CSA-39)
#
# main.py 에서 "/api" 아래 등록. 고객 도메인(nginx)은 /api/tickets(상담원용)를 막고 이것만 연다.
# - POST /api/inquiries InquiryIn → CustomerInquiry  문의 제출. thread_ref 가 처음 문의와 같으면
#   고객 회신(추가정보 보내기)이다 (services/tickets.py submit → reply). 고객 화면이 만들어 둔다.
# - GET /api/inquiries/{ticket_id} → CustomerInquiry  고객이 볼 상태와 받은 회신만
#   /api/tickets/{id}(상담원용)와 달리 AI 초안·근거·점검 결과·담당자·부서는 내보내지 않는다.
#   상담원이 승인해 보낸 글(final_reply: 답변 또는 추가정보 요청)만 message 로 준다.
#
# 정해 둔 것
# - 고객 상태는 5가지: RECEIVED(접수, 아직 분석 전) · IN_PROGRESS(분석·검토·이관 중) ·
#   WAITING_CUSTOMER(추가정보 요청을 받음) · ANSWERED(답변 발송) · CLOSED(해결·반려)
# - 로그인이 아직 없어 ticket_id 를 아는 사람은 조회할 수 있다 (id 는 추측하기 어려운 12자리).
#   로그인이 생기면 customer_id 로 막는다.
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from cs_agent.api.deps import Tickets
from cs_agent.domain import TicketStatus
from cs_agent.schemas import InquiryIn, TicketOut
from cs_agent.services.tickets import TicketNotFound

router = APIRouter(prefix="/inquiries", tags=["inquiries"])

CustomerStatus = Literal["RECEIVED", "IN_PROGRESS", "WAITING_CUSTOMER", "ANSWERED", "CLOSED"]

_STATUS: dict[TicketStatus, CustomerStatus] = {
    TicketStatus.NEW: "RECEIVED",
    TicketStatus.WAITING_CUSTOMER: "WAITING_CUSTOMER",
    TicketStatus.APPROVED: "ANSWERED",
    TicketStatus.RESOLVED: "CLOSED",
    TicketStatus.REJECTED: "CLOSED",
}
# 고객에게 보낸 글이 있는 상태 (반려는 보낸 글이 없다)
_SENT = frozenset({TicketStatus.WAITING_CUSTOMER, TicketStatus.APPROVED, TicketStatus.RESOLVED})


class CustomerInquiry(BaseModel):
    ticket_id: str
    subject: str
    body: str
    received_at: datetime | None
    status: CustomerStatus
    message: str | None = None  # 상담원이 보낸 회신 (고객 언어)
    message_language: str | None = None


@router.post("", response_model=CustomerInquiry, status_code=201)
def submit_inquiry(inquiry: InquiryIn, tickets: Tickets) -> CustomerInquiry:
    return _customer_view(tickets.submit(inquiry))


@router.get("/{ticket_id}", response_model=CustomerInquiry)
def customer_inquiry(ticket_id: str, tickets: Tickets) -> CustomerInquiry:
    try:
        return _customer_view(tickets.get(ticket_id))
    except TicketNotFound as e:
        raise HTTPException(404, f"inquiry {ticket_id} not found") from e


def _customer_view(ticket: TicketOut) -> CustomerInquiry:
    inquiry = ticket.inquiry
    sent = ticket.status in _SENT and ticket.final_reply
    return CustomerInquiry(
        ticket_id=ticket.ticket_id,
        subject=inquiry.subject if inquiry else "",
        body=inquiry.body if inquiry else "",
        received_at=inquiry.received_at if inquiry else None,
        status=_STATUS.get(ticket.status, "IN_PROGRESS"),
        message=ticket.final_reply if sent else None,
        message_language=ticket.final_reply_language if sent else None,
    )
