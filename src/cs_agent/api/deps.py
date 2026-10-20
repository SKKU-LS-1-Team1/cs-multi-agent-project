# FastAPI 의존성 (CSA-21 · 담당 김동규)
#
# 요청마다 app.state 의 공유 객체를 꺼내 라우터에 넘긴다 (main.py 가 만들어 둔다).
# ruff B008 규칙 때문에 기본값에 Depends() 를 쓰지 말고 Annotated 로 만든다.
# TODO: ChatSessions(cache/store.py, CSA-45), Docs(agents/retrieval.py, CSA-28),
#   DB 세션(db/session.py, CSA-24) 은 해당 모듈이 생기면 여기에 같은 모양으로 추가한다.
from typing import Annotated

from fastapi import Depends, Request

from cs_agent.llm.router import LLMRouter
from cs_agent.services.tickets import TicketService


def _tickets(request: Request) -> TicketService:
    return request.app.state.tickets


def _llm(request: Request) -> LLMRouter:
    return request.app.state.llm


Tickets = Annotated[TicketService, Depends(_tickets)]
LLM = Annotated[LLMRouter, Depends(_llm)]
