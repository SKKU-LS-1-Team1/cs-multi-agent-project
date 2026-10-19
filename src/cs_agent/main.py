"""FastAPI 진입점 (CSA-21). 실행: `uv run uvicorn cs_agent.main:app --reload`"""

from fastapi import FastAPI

from cs_agent import __version__
from cs_agent.agents.retrieval import default_retrievers
from cs_agent.api import chat, dashboard, products, tickets
from cs_agent.cache.store import ChatSessionStore
from cs_agent.graph.builder import GraphDeps
from cs_agent.llm.router import get_router
from cs_agent.services.tickets import TicketService


def create_app(deps: GraphDeps | None = None) -> FastAPI:
    app = FastAPI(title="C/S Multi-Agent", version=__version__, root_path="")
    if deps is None:
        docs, cases = default_retrievers()
        deps = GraphDeps(llm=get_router(), docs=docs, cases=cases)
    app.state.llm = deps.llm
    app.state.docs = deps.docs
    app.state.tickets = TicketService(deps)
    app.state.chat_sessions = ChatSessionStore()

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok", "version": __version__}

    for r in (tickets.router, chat.router, products.router, dashboard.router):
        app.include_router(r, prefix="/api")
    return app


app = create_app()
