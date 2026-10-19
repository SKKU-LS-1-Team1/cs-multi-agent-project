"""요청마다 공유 객체를 꺼낸다. 객체는 main.create_app()에서 app.state에 만든다."""

from typing import Annotated

from fastapi import Depends, Request

from cs_agent.agents.retrieval import Retriever
from cs_agent.cache.store import ChatSessionStore
from cs_agent.llm.router import LLMRouter
from cs_agent.services.tickets import TicketService


def _service(request: Request) -> TicketService:
    return request.app.state.tickets


def _chat_store(request: Request) -> ChatSessionStore:
    return request.app.state.chat_sessions


def _docs(request: Request) -> Retriever:
    return request.app.state.docs


def _llm(request: Request) -> LLMRouter:
    return request.app.state.llm


Tickets = Annotated[TicketService, Depends(_service)]
ChatSessions = Annotated[ChatSessionStore, Depends(_chat_store)]
Docs = Annotated[Retriever, Depends(_docs)]
LLM = Annotated[LLMRouter, Depends(_llm)]
