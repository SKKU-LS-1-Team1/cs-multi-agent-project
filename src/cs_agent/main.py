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
#   - Redis 가 붙으면 챗봇 대화와 LLM 캐시·호출 횟수(live 일 때, cache/store.py)를 Redis 에 둔다.
#   - 안 붙으면 APP_ENV=local 은 경고 후 메모리로 돈다 (서버를 다시 켜면 사라짐), prod 는 멈춘다.
# - GET /api/health → {"status": "ok", "version": ...}
# - 라우터는 모두 prefix "/api". Nginx(infra/nginx/nginx.conf)가 /api 요청을 이 앱으로 넘긴다.
# - 시작 시 기준표와 담당자 명단을 읽는다 (rules/tables.py, services/assignment.py — 표가 틀리면
#   여기서 멈춘다).
#   종료 시 남은 Langfuse 기록을 보낸다.
# - 분석 대기(ANALYSIS_PENDING) 문의를 analysis_retry_interval_s 마다 다시 돌린다 (0 이면 끔).
# - 피드백 루프 (CSA-15, agents/case_memory.py): 벡터 없이 저장된 해결 사례를 case_embed_interval_s
#   마다 임베딩한다 (live·DB 일 때). 사례 검색기가 키워드 검색이면 운영 중 해결 사례도 같이 찾게
#   감싼다 (with_live_cases).
# - 지식 그래프 (CSA-71·72, agents/knowledge_graph.py): GRAPH_ENABLED 이고 Neo4j 에 붙으면 ⑧ 근거
#   확정의 사례를 그래프에서 찾고, 해결 확정 사례를 그래프에도 학습한다 (with_graph_learning).
#   붙지 못하면 경고만 남기고 패턴 DB 로 돈다. 테스트는 create_app(graph=가짜) 로 넣는다.
import asyncio
import logging
from collections.abc import AsyncIterator, Callable
from contextlib import ExitStack, asynccontextmanager, suppress
from functools import partial
from typing import Any, Literal

from fastapi import FastAPI

from cs_agent import __version__
from cs_agent.agents import knowledge_graph
from cs_agent.agents.case_memory import with_graph_learning, with_live_cases
from cs_agent.agents.retrieval import default_retrievers
from cs_agent.api import agents as agents_api
from cs_agent.api import chat, customers, dashboard, inquiries, products, progress, tickets
from cs_agent.cache.store import ChatSessionStore, MemoryKV, connect_redis
from cs_agent.config import Settings, get_settings
from cs_agent.graph.builder import GraphDeps, build_ticket_graph, postgres_checkpointer
from cs_agent.llm import tracing
from cs_agent.llm.router import LLMRouter, get_router
from cs_agent.rules.tables import load_tables
from cs_agent.services.assignment import load_agents
from cs_agent.services.progress import ProgressService
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


async def _embed_cases_loop(records: Any, interval_s: float) -> None:
    """벡터 없이 저장된 해결 사례를 채운다. 시작하자마자 한 번, 그다음 interval_s 마다."""
    while True:
        try:
            filled = await asyncio.to_thread(records.embed_missing_cases)
        except Exception:
            _LOGGER.exception("해결 사례 임베딩 채우기 실패")
        else:
            if filled:
                _LOGGER.info("벡터 없던 해결 사례 %d건 임베딩", filled)
        await asyncio.sleep(interval_s)


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
    graph: Any = None,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        settings = get_settings()
        tables = load_tables()
        roster = load_agents()  # 담당자 명단 (CSA-53). 표가 틀리면 여기서 멈춘다
        app.state.llm = llm or get_router()
        app.state.docs, app.state.cases = retrievers or _retrievers()
        # 검색기를 넘긴 테스트는 설정과 상관없이 그래프를 켜지 않는다 (넘긴 graph 만 쓴다)
        owns_graph = graph is None and retrievers is None
        app.state.graph = knowledge_graph.default_graph() if owns_graph else graph

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
            # LLM 같은 요청 캐시·분당 호출 제한 (CSA-45). 테스트가 넘긴 라우터는 건드리지 않는다
            if llm is None and app.state.llm.enabled:
                app.state.llm.kv = redis_client if redis_client is not None else MemoryKV()

            # 키워드 사례 검색(로컬)도 운영 중 해결 사례를 찾게 (CSA-15 피드백 루프)
            app.state.cases = with_live_cases(app.state.cases, records)
            records = with_graph_learning(records, app.state.graph)  # CSA-72
            if owns_graph:
                stack.callback(knowledge_graph.close, app.state.graph)
            deps = GraphDeps(
                llm=app.state.llm,
                tables=tables,
                docs=app.state.docs,
                cases=app.state.cases,
                graph=app.state.graph,
                **(agents or {}),
            )
            app.state.tickets = TicketService(
                build_ticket_graph(deps, checkpointer),
                records,
                roster,
                escalation_writer=partial(deps.write_escalation_request, llm=deps.llm),
            )
            app.state.progress = ProgressService(
                app.state.tickets, app.state.llm, check_customer_qc=deps.check_customer_qc
            )
            interval = settings.analysis_retry_interval_s
            retry = (
                asyncio.create_task(_retry_pending_loop(app.state.tickets, interval))
                if interval > 0
                else None
            )
            embed_interval = settings.case_embed_interval_s
            embed_cases = (
                asyncio.create_task(_embed_cases_loop(records, embed_interval))
                if embed_interval > 0 and getattr(records, "embed_fn", None) is not None
                else None
            )
            yield
            for task in (retry, embed_cases):
                if task:
                    task.cancel()
                    with suppress(asyncio.CancelledError):
                        await task
            if redis_client is not None:
                redis_client.close()
            tracing.flush()

    app = FastAPI(title="C/S multi-agent", version=__version__, lifespan=lifespan)

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok", "version": __version__}

    for module in (tickets, inquiries, chat, products, dashboard, agents_api, progress, customers):
        app.include_router(module.router, prefix="/api")
    return app


app = create_app()
