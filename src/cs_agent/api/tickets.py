"""문의 접수·조회·상담원 처리 API (CSA-21 · CSA-25 · CSA-40)."""

from fastapi import APIRouter, HTTPException

from cs_agent.api.deps import Tickets
from cs_agent.schemas import InquiryIn, ReviewIn, TicketOut

router = APIRouter(prefix="/tickets", tags=["tickets"])


@router.post("", response_model=TicketOut)
def submit(inquiry: InquiryIn, svc: Tickets) -> TicketOut:
    """문의 접수 → 그래프 실행. 상담원 검토 지점에서 멈춘 상태로 돌아온다."""
    return svc.submit(inquiry)


@router.get("")
def work_list(svc: Tickets, dept: str | None = None) -> list[dict]:
    """상담원 작업 목록 (SLA 순 정렬, 75% 경고)."""
    return svc.work_list(dept)


@router.get("/{ticket_id}", response_model=TicketOut)
def get_ticket(ticket_id: str, svc: Tickets) -> TicketOut:
    try:
        return svc.get(ticket_id)
    except KeyError as e:
        raise HTTPException(404, "ticket not found") from e


@router.post("/{ticket_id}/action", response_model=TicketOut)
def act(ticket_id: str, review: ReviewIn, svc: Tickets) -> TicketOut:
    """승인 · 수정 후 승인 · AI 재작성 · 추가정보 요청 · 전문부서 이관 · 반려."""
    try:
        return svc.act(ticket_id, review)
    except KeyError as e:
        raise HTTPException(404, "ticket not found") from e


@router.post("/{ticket_id}/resolve", response_model=TicketOut)
def resolve(ticket_id: str, svc: Tickets) -> TicketOut:
    """해결 확정. 사례 DB 저장 대상이면 저장한다 (기획서 7.1)."""
    return svc.resolve(ticket_id)
