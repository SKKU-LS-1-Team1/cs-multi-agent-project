# 고객용 문의 API (CSA-61 · CSA-46 · 담당 김동규) — 고객 화면 문의하기·내 문의 내역 (CSA-39)
#
# main.py 에서 "/api" 아래 등록. 고객 도메인(nginx)은 /api/tickets(상담원용)를 막고 이것만 연다.
# - POST /api/inquiries InquiryIn → CustomerInquiry  문의 제출. thread_ref 가 처음 문의와 같으면
#   고객 회신(추가정보 보내기)이다 (services/tickets.py submit → reply). 고객 화면이 만들어 둔다.
# - GET /api/inquiries/{ticket_id} → CustomerInquiry  고객이 볼 상태와 받은 회신만
#   /api/tickets/{id}(상담원용)와 달리 AI 초안·근거·점검 결과·담당자·부서는 내보내지 않는다.
#   상담원이 승인해 보낸 글(final_reply: 답변 또는 추가정보 요청)만 message 로 준다.
# - POST /api/inquiries/{ticket_id}/attachments?name=…  첨부 한 개. 본문이 파일 내용 그대로이고
#   Content-Type 이 파일 형식이다 (multipart 를 쓰지 않아 의존성이 늘지 않는다). → Attachment
# - GET  /api/inquiries/{ticket_id}/attachments → list[Attachment]  내 문의 · 상담원 화면
# - GET  /api/inquiries/{ticket_id}/attachments/{attachment_id}  파일.
#   안전한 그림만 화면 안에서 연다 (services/attachments.py INLINE_TYPES), 나머지는 내려받기.
#
# 정해 둔 것
# - 고객 상태는 5가지: RECEIVED(접수, 아직 분석 전) · IN_PROGRESS(분석·검토·이관 중) ·
#   WAITING_CUSTOMER(추가정보 요청을 받음) · ANSWERED(답변 발송) · CLOSED(해결·반려)
# - 로그인이 아직 없어 ticket_id 를 아는 사람은 조회할 수 있다 (id 는 추측하기 어려운 12자리).
#   로그인이 생기면 customer_id 로 막는다.
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

from cs_agent.api.deps import Attachments, Tickets
from cs_agent.domain import TicketStatus
from cs_agent.schemas import InquiryIn, TicketOut
from cs_agent.services.attachments import (
    INLINE_TYPES,
    MAX_BYTES,
    Attachment,
    AttachmentError,
)
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
    # 예상 소요시간 안내용 SLA 목표 (시간). 고객 대기 시간은 빠진다
    first_response_target_h: float | None = None
    resolution_target_h: float | None = None


@router.post("", response_model=CustomerInquiry, status_code=201)
def submit_inquiry(inquiry: InquiryIn, tickets: Tickets) -> CustomerInquiry:
    return _customer_view(tickets.submit(inquiry))


@router.get("/{ticket_id}", response_model=CustomerInquiry)
def customer_inquiry(ticket_id: str, tickets: Tickets) -> CustomerInquiry:
    try:
        return _customer_view(tickets.get(ticket_id))
    except TicketNotFound as e:
        raise HTTPException(404, f"inquiry {ticket_id} not found") from e


def _known(tickets: Tickets, ticket_id: str) -> None:
    if not tickets.records.exists(ticket_id):
        raise HTTPException(404, f"inquiry {ticket_id} not found")


@router.post("/{ticket_id}/attachments", response_model=Attachment, status_code=201)
async def upload_attachment(
    ticket_id: str, name: str, request: Request, tickets: Tickets, store: Attachments
) -> Attachment:
    _known(tickets, ticket_id)
    length = request.headers.get("content-length") or "0"
    if length.isdigit() and int(length) > MAX_BYTES:
        raise HTTPException(413, "file too large")
    # 큰 영상도 메모리에 다 올리지 않게 받으면서 임시 파일에 쓴다
    tmp = store.upload_path(ticket_id)
    try:
        size = 0
        with tmp.open("wb") as out:
            async for chunk in request.stream():
                size += len(chunk)
                if size > MAX_BYTES:
                    raise HTTPException(413, "file too large")
                out.write(chunk)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    content_type = request.headers.get("content-type") or "application/octet-stream"
    try:
        return store.commit(ticket_id, tmp, name, content_type)
    except AttachmentError as e:
        raise HTTPException(422, str(e)) from e


@router.get("/{ticket_id}/attachments", response_model=list[Attachment])
def list_attachments(ticket_id: str, tickets: Tickets, store: Attachments) -> list[Attachment]:
    _known(tickets, ticket_id)
    return store.list(ticket_id)


@router.get("/{ticket_id}/attachments/{attachment_id}")
def get_attachment(
    ticket_id: str, attachment_id: str, tickets: Tickets, store: Attachments
) -> FileResponse:
    _known(tickets, ticket_id)
    try:
        meta, path = store.open(ticket_id, attachment_id)
    except KeyError as e:
        raise HTTPException(404, f"attachment {attachment_id} not found") from e
    inline = meta.content_type in INLINE_TYPES
    return FileResponse(
        path,
        media_type=meta.content_type if inline else "application/octet-stream",
        filename=meta.name,
        content_disposition_type="inline" if inline else "attachment",
        headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "private, max-age=86400"},
    )


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
        first_response_target_h=ticket.sla_first_response_h,
        resolution_target_h=ticket.sla_resolution_h,
    )
