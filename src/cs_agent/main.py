# FastAPI 진입점 (CSA-21 · 담당 김동규 · Sprint 1)
# 실행: uv run uvicorn cs_agent.main:app --reload  → http://localhost:8000/docs
#
# - create_app(): 공유 객체를 app.state 에 둔다. 테스트는 create_app(llm=가짜 라우터) 로 만든다.
#   app.state.llm(llm/router.py), app.state.tickets(services/tickets.py, 그래프 포함)
# - GET /api/health → {"status": "ok", "version": ...}
# - 라우터는 모두 prefix "/api". Nginx(infra/nginx/nginx.conf)가 /api 요청을 이 앱으로 넘긴다.
# - 시작 시 기준표를 읽는다 (rules/tables.py, 표가 틀리면 여기서 멈춘다).
#   종료 시 남은 Langfuse 기록을 보낸다.
# TODO: app.state.docs·cases(agents/retrieval.py default_retrievers, CSA-28),
#   app.state.chat_sessions(cache/store.py, CSA-45), 시작 시 DB 확인(db/session.py, CSA-24)
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from cs_agent import __version__
from cs_agent.api import chat, dashboard, products, tickets
from cs_agent.graph.builder import GraphDeps, build_ticket_graph
from cs_agent.llm import tracing
from cs_agent.llm.router import LLMRouter, get_router
from cs_agent.rules.tables import load_tables
from cs_agent.services.tickets import TicketService


def create_app(llm: LLMRouter | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        tables = load_tables()
        app.state.llm = llm or get_router()
        app.state.tickets = TicketService(
            build_ticket_graph(GraphDeps(llm=app.state.llm, tables=tables))
        )
        yield
        tracing.flush()

    app = FastAPI(title="C/S multi-agent", version=__version__, lifespan=lifespan)

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok", "version": __version__}

    for module in (tickets, chat, products, dashboard):
        app.include_router(module.router, prefix="/api")
    return app


app = create_app()
