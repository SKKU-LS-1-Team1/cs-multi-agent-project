# FastAPI 의존성 (CSA-21 · 담당 김동규)
#
# 요청마다 app.state 의 공유 객체를 꺼내 라우터에 넘긴다 (main.py 가 만들어 둔다).
# ruff B008 규칙 때문에 기본값에 Depends() 를 쓰지 말고 Annotated 로 만든다.
#
# | 이름 | 객체 | 만든 곳 |
# |---|---|---|
# | Tickets | services/tickets.TicketService | main.py |
# | LLM | llm/router.LLMRouter | main.py |
# | Docs · Cases | agents/retrieval.Retriever (없으면 None) | agents/retrieval.default_retrievers |
# | ChatSessions | cache/store.ChatSessionStore (Redis, 없으면 메모리) | main.py |
# | DB | sqlalchemy Session (요청 끝나면 닫음). DB 없이 켜졌으면 503 | db/session.py |
from collections.abc import Iterator
from typing import Annotated, Any

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from cs_agent.cache.store import ChatSessionStore
from cs_agent.llm.router import LLMRouter
from cs_agent.services.mailbox import Mailbox as MailboxService
from cs_agent.services.tickets import TicketService


def _tickets(request: Request) -> TicketService:
    return request.app.state.tickets


def _llm(request: Request) -> LLMRouter:
    return request.app.state.llm


def _docs(request: Request) -> Any:
    return request.app.state.docs


def _cases(request: Request) -> Any:
    return request.app.state.cases


def _mailbox(request: Request) -> MailboxService:
    return request.app.state.mailbox


def _chat_sessions(request: Request) -> ChatSessionStore:
    return request.app.state.chat_sessions


def _db(request: Request) -> Iterator[Session]:
    sessionmaker = request.app.state.sessionmaker
    if sessionmaker is None:
        raise HTTPException(503, "database is not connected")
    with sessionmaker() as session:
        yield session


Tickets = Annotated[TicketService, Depends(_tickets)]
LLM = Annotated[LLMRouter, Depends(_llm)]
Docs = Annotated[Any, Depends(_docs)]
Cases = Annotated[Any, Depends(_cases)]
ChatSessions = Annotated[ChatSessionStore, Depends(_chat_sessions)]
DB = Annotated[Session, Depends(_db)]
Mailbox = Annotated[MailboxService, Depends(_mailbox)]
