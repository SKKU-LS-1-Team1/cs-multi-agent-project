# 문의 접수 · 조회 · 상담원 처리 API (CSA-21 · CSA-25 · CSA-40 · 담당 김동규)
#
# main.py 에서 "/api" 아래 등록. 일은 services/tickets.py 가 한다.
# - POST /api/tickets                     InquiryIn → TicketOut  문의 접수 → 그래프 실행
#     (고객 문의하기 화면 CSA-39, mock 데이터 CSA-23, 평가 스크립트 CSA-50 이 쓴다)
# - GET  /api/tickets?dept=               → list[dict]  상담원 작업 목록 (SLA 순, 75% 경고, CSA-40)
# - GET  /api/tickets/answered            → list[str]  답변은 보냈고 아직 해결 확정 전(APPROVED)인
#     문의 (CSA-61). 작업 목록은 APPROVED 를 닫힌 건으로 빼므로, 관리자 화면이 '처리 결과 기록 및
#     완료'를 누를 문의를 여기서 찾는다.
# - GET  /api/tickets/{ticket_id}         → TicketOut  검토 화면 (초안·근거·점검 결과, CSA-41·42)
# - POST /api/tickets/{ticket_id}/escalation-request → 요청서 생성/재생성 (CSA-55).
#   {"to_dept": "CERT"} 또는 생략하면 규칙의 이관 부서. 실패는 503, 상태는 유지.
# - POST /api/tickets/{ticket_id}/action  ReviewIn → TicketOut  승인·수정 후 승인·AI 재작성·
#     추가정보 요청·이관·반려 (CSA-25)
# - POST /api/tickets/{ticket_id}/resolve → TicketOut  해결 확정 → 사례 저장 (기획서 7.1)
# - POST /api/tickets/{ticket_id}/assign  AssignIn → TicketOut  같은 부서 다른 담당자로 넘기기
#     (CSA-53·54). 다른 부서·없는·비활성 담당자, 닫힌 문의는 409
# - GET  /api/tickets/{ticket_id}/assignments → list[dict]  배정 이력 (오래된 순)
# - GET  /api/tickets?assignee=           → 그 담당자 건만 (부서 필터와 같이 써도 된다)
# 없는 ticket_id 는 404, 지금 상태에서 못 하는 처리는 409.
from collections.abc import Iterator
from contextlib import contextmanager

from fastapi import APIRouter, HTTPException

from cs_agent.agents.escalation import EscalationError
from cs_agent.api.deps import Tickets
from cs_agent.schemas import AssignIn, EscalationRequestIn, InquiryIn, ReviewIn, TicketOut
from cs_agent.services.tickets import InvalidAction, TicketNotFound

router = APIRouter(prefix="/tickets", tags=["tickets"])


@contextmanager
def _errors() -> Iterator[None]:
    try:
        yield
    except TicketNotFound as e:
        raise HTTPException(404, f"ticket {e} not found") from e
    except InvalidAction as e:
        raise HTTPException(409, str(e)) from e
    except EscalationError as e:
        raise HTTPException(503, str(e)) from e


@router.post("", response_model=TicketOut, status_code=201)
def submit(inquiry: InquiryIn, tickets: Tickets) -> TicketOut:
    return tickets.submit(inquiry)


@router.get("")
def work_list(tickets: Tickets, dept: str | None = None, assignee: str | None = None) -> list[dict]:
    return tickets.work_list(dept, assignee=assignee)


# /{ticket_id} 보다 먼저 둔다 (answered 가 ticket_id 로 잡히지 않게)
@router.get("/answered")
def answered(tickets: Tickets) -> list[str]:
    return tickets.answered()


@router.get("/{ticket_id}", response_model=TicketOut)
def get_ticket(ticket_id: str, tickets: Tickets) -> TicketOut:
    with _errors():
        return tickets.get(ticket_id)


@router.post("/{ticket_id}/action", response_model=TicketOut)
def act(ticket_id: str, review: ReviewIn, tickets: Tickets) -> TicketOut:
    with _errors():
        return tickets.act(ticket_id, review)


@router.post("/{ticket_id}/escalation-request", response_model=TicketOut)
def generate_escalation_request(
    ticket_id: str, tickets: Tickets, body: EscalationRequestIn | None = None
) -> TicketOut:
    """CSA-55: 요청서 생성/재생성. GET /tickets/{id}로 다시 조회. 실제 이관은 /action."""
    with _errors():
        return tickets.generate_escalation_request(ticket_id, body.to_dept if body else None)


@router.post("/{ticket_id}/resolve", response_model=TicketOut)
def resolve(ticket_id: str, tickets: Tickets) -> TicketOut:
    with _errors():
        return tickets.resolve(ticket_id)


@router.post("/{ticket_id}/assign", response_model=TicketOut)
def assign(ticket_id: str, change: AssignIn, tickets: Tickets) -> TicketOut:
    with _errors():
        return tickets.assign(ticket_id, change)


@router.get("/{ticket_id}/assignments")
def assignments(ticket_id: str, tickets: Tickets) -> list[dict]:
    with _errors():
        return tickets.assignments(ticket_id)
