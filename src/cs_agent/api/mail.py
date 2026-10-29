# 업무 메일함 API (CSA-74 · services/mailbox.py). 관리자 화면 "업무 메일" 이 쓴다.
#
# main.py 에서 "/api" 아래 등록. 고객 도메인 nginx 는 허용 목록 밖이라 막힌다 (CSA-46).
# - GET  /api/mail                     → list[MailOut]  메일 목록 (최근 것 위, 등록했으면 ticket_id)
# - GET  /api/mail/{mail_id}           → MailOut
# - POST /api/mail/{mail_id}/analyze   MailAnalyzeIn → MailAnalysis
#   AI 분석 + 부서·우선순위 (티켓은 만들지 않는다)
# - POST /api/mail/{mail_id}/register  MailRegisterIn → TicketOut (201)
#   검토한 유형·제품으로 티켓 등록
from collections.abc import Iterator
from contextlib import contextmanager

from fastapi import APIRouter, HTTPException

from cs_agent.api.deps import Mailbox
from cs_agent.schemas import TicketOut
from cs_agent.services.mailbox import (
    MailAnalysis,
    MailAnalyzeIn,
    MailNotFound,
    MailOut,
    MailRegisterIn,
)

router = APIRouter(prefix="/mail", tags=["mail"])


@contextmanager
def _errors() -> Iterator[None]:
    try:
        yield
    except MailNotFound as e:
        raise HTTPException(404, f"mail {e} not found") from e


@router.get("", response_model=list[MailOut])
def mails(mailbox: Mailbox) -> list[MailOut]:
    return mailbox.list()


@router.get("/{mail_id}", response_model=MailOut)
def mail(mail_id: str, mailbox: Mailbox) -> MailOut:
    with _errors():
        return mailbox.get(mail_id)


@router.post("/{mail_id}/analyze", response_model=MailAnalysis)
def analyze(mail_id: str, mailbox: Mailbox, change: MailAnalyzeIn | None = None) -> MailAnalysis:
    with _errors():
        return mailbox.analyze(mail_id, change)


@router.post("/{mail_id}/register", response_model=TicketOut, status_code=201)
def register(mail_id: str, body: MailRegisterIn, mailbox: Mailbox) -> TicketOut:
    with _errors():
        return mailbox.register(mail_id, body)
