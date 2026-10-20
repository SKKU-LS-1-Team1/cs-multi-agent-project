# FastAPI 진입점 (CSA-21 · 담당 김동규 · Sprint 1)
# 실행: uv run uvicorn cs_agent.main:app --reload  → http://localhost:8000/docs
#
# - create_app(): 공유 객체를 app.state 에 둔다. 테스트는 create_app(llm=가짜 라우터,
#   agents={"classify": ...}, storage="memory", retrievers=(None, None)) 로 에이전트 자리·저장소·
#   검색기를 바꿔 만든다 (agents 키는 GraphDeps 필드 이름).
#   app.state.llm(llm/router.py), app.state.tickets(services/tickets.py, 그래프 포함),
#   app.state.docs·cases(agents/retrieval.py), app.state.chat_sessions(cache/store.py),
#   app.state.sessionmaker(db/session.py, DB 없으면 None). 꺼내 쓰는 쪽은 api/deps.py.
# - 저장소 (storage="auto"): 시작할 때 DB·Redis 에 붙어 본다.
#   - DB 가 붙고 스키마가 최신(alembic head)이면 PostgresSaver 체크포인트 + SqlRecords 로 기록한다.
#   - Redis 가 붙으면 챗봇 대화를 Redis 에 둔다.
#   - 안 붙으면 APP_ENV=local 은 경고 후 메모리로 돈다 (서버를 다시 켜면 사라짐), prod 는 멈춘다.
# - GET /api/health → {"status": "ok", "version": ...}
# - 라우터는 모두 prefix "/api". Nginx(infra/nginx/nginx.conf)가 /api 요청을 이 앱으로 넘긴다.
# - 시작 시 기준표를 읽는다 (rules/tables.py, 표가 틀리면 여기서 멈춘다).
#   종료 시 남은 Langfuse 기록을 보낸다.
# - 분석 대기(ANALYSIS_PENDING) 문의를 analysis_retry_interval_s 마다 다시 돌린다 (0 이면 끔).
import asyncio
import logging
from collections.abc import AsyncIterator, Callable
from contextlib import ExitStack, asynccontextmanager, suppress
from typing import Any, Literal

from fastapi import FastAPI

from cs_agent import __version__
from cs_agent.agents.retrieval import default_retrievers
from cs_agent.api import chat, dashboard, products, tickets
from cs_agent.cache.store import ChatSessionStore, connect_redis
from cs_agent.config import Settings, get_settings
from cs_agent.graph.builder import GraphDeps, build_ticket_graph, postgres_checkpointer
from cs_agent.llm import tracing
from cs_agent.llm.router import LLMRouter, get_router
from cs_agent.rules.tables import load_tables
from cs_agent.services.records import MemoryRecords, SqlRecords
from cs_agent.services.tickets import TicketService

_LOGGER = logging.getLogger(__name__)


async def _retry_pending_loop(service: TicketService, interval_s: float) -> None:
    while True:
        await asyncio.sleep(interval_s)
        try:
            recovered = await asyncio.to_thread(service.retry_pending)
        except Exception:
            _LOGGER.exception("분석 대기 문의 재시도 실패")
            continue
        if recovered:
            _LOGGER.info("분석 대기 해소: %s", recovered)


def _unavailable(settings: Settings, what: str, error: Exception) -> None:
    """로컬은 메모리로 대체하고, 운영은 시작을 멈춘다."""
    if settings.app_env == "prod":
        raise RuntimeError(f"{what} 연결 실패") from error
    _LOGGER.warning("%s 연결 실패 → 메모리로 대체 (서버를 다시 켜면 사라짐): %s", what, error)


def _connect_db(settings: Settings) -> Any:
    """DB 에 붙고 스키마가 최신인지 본다. 세션 공장을 돌려준다."""
    from alembic.runtime.migration import MigrationContext
    from alembic.script import ScriptDirectory

    from cs_agent.db.session import alembic_config, get_engine, get_sessionmaker

    with get_engine().connect() as conn:
        current = MigrationContext.configure(conn).get_current_revision()
    head = ScriptDirectory.from_config(alembic_config()).get_current_head()
    if current != head:
        raise RuntimeError(
            f"DB 스키마가 최신이 아님 ({current} → {head}): uv run alembic upgrade head"
        )
    return get_sessionmaker()


def _retrievers() -> tuple[Any, Any]:
    try:
        return default_retrievers()
    except Exception:  # 검색 대상 데이터가 없어도 서버는 뜬다 (근거 없이 답변·점검)
        _LOGGER.exception("검색기 준비 실패 → 근거 검색 없이 시작")
        return None, None


def create_app(
    llm: LLMRouter | None = None,
    agents: dict[str, Callable] | None = None,
    *,
    storage: Literal["auto", "memory"] = "auto",
    retrievers: tuple[Any, Any] | None = None,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        settings = get_settings()
        tables = load_tables()
        app.state.llm = llm or get_router()
        app.state.docs, app.state.cases = retrievers or _retrievers()

        with ExitStack() as stack:
            app.state.sessionmaker = None
            checkpointer = None
            records = MemoryRecords()
            if storage == "auto":
                try:
                    app.state.sessionmaker = _connect_db(settings)
                    checkpointer = stack.enter_context(postgres_checkpointer(settings.database_url))
                    embed_fn = None
                    if settings.llm_provider == "live":
                        from cs_agent.pipeline.embed_docs import embed as embed_fn
                    records = SqlRecords(app.state.sessionmaker, embed_fn=embed_fn)
                except Exception as e:
                    app.state.sessionmaker = None
                    _unavailable(settings, "PostgreSQL", e)

            redis_client = None
            if storage == "auto":
                try:
                    redis_client = connect_redis(settings.redis_url)
                except Exception as e:
                    _unavailable(settings, "Redis", e)
            app.state.chat_sessions = ChatSessionStore(redis_client)

            deps = GraphDeps(
                llm=app.state.llm,
                tables=tables,
                docs=app.state.docs,
                cases=app.state.cases,
                **(agents or {}),
            )
            app.state.tickets = TicketService(build_ticket_graph(deps, checkpointer), records)
            interval = settings.analysis_retry_interval_s
            retry = (
                asyncio.create_task(_retry_pending_loop(app.state.tickets, interval))
                if interval > 0
                else None
            )
            yield
            if retry:
                retry.cancel()
                with suppress(asyncio.CancelledError):
                    await retry
            if redis_client is not None:
                redis_client.close()
            tracing.flush()

    app = FastAPI(title="C/S multi-agent", version=__version__, lifespan=lifespan)

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok", "version": __version__}

    for module in (tickets, chat, products, dashboard):
        app.include_router(module.router, prefix="/api")
    return app


app = create_app()
