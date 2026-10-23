"""Progress notice preparation API. This router does not send customer messages."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request

from cs_agent.api.tickets import _errors
from cs_agent.progress_schemas import ProgressApprovalIn, ProgressNotice, ProgressNoticeIn
from cs_agent.services.progress import ProgressService

router = APIRouter(prefix="/tickets", tags=["progress-notices"])


def _service(request: Request) -> ProgressService:
    return request.app.state.progress


Progress = Annotated[ProgressService, Depends(_service)]


@router.get("/{ticket_id}/progress-notices", response_model=list[ProgressNotice])
def list_notices(ticket_id: str, progress: Progress) -> list[ProgressNotice]:
    with _errors():
        return progress.list(ticket_id)


@router.post("/{ticket_id}/progress-notices", response_model=ProgressNotice)
def create_notice(ticket_id: str, body: ProgressNoticeIn, progress: Progress) -> ProgressNotice:
    with _errors():
        return progress.create(ticket_id, body)


@router.post("/{ticket_id}/progress-notices/{notice_id}/approve", response_model=ProgressNotice)
def approve_notice(
    ticket_id: str, notice_id: UUID, body: ProgressApprovalIn, progress: Progress
) -> ProgressNotice:
    with _errors():
        return progress.approve(ticket_id, str(notice_id), body)
