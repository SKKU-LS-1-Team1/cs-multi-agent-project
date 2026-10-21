# Langfuse 기록 (CSA-48 · 담당 김동규 · Sprint 1)
#
# 모든 LLM 호출을 남긴다. K1(처리 지연 p95)과 Jev·Gemini 비교(기획서 9.2)를 이 기록으로 잰다.
#
# - trace(task, model, prompt, **metadata): with 문으로 감싼다. 끝날 때 Langfuse 에
#   generation(name=task, model, input, output, 지연 시간, 토큰) 을 남긴다. 지연 시간은 Langfuse 가
#   시작·종료 시각으로 잰다. 비용은 Langfuse 가 모델 이름과 토큰으로 계산한다.
# - 키(settings.langfuse_public_key / secret_key)가 없으면 기록하지 않는다.
#   langfuse 패키지(extra: obs)도 키가 있을 때만 불러온다. 키는 있는데 패키지가 없거나 클라이언트를
#   만들지 못하면 경고를 한 번 남기고 기록만 건너뛴다 — LLM 호출은 그대로 간다 (기록 장애로
#   분석이 실패해 문의가 전부 분석 대기가 되던 문제, PR #31).
# - ticket_scope(ticket_id): 문의 1건의 노드 실행 전체를 하나의 trace 로 묶는다.
#   그래프 실행을 이걸로 감싸면 안에서 일어난 호출이 모두 같은 trace
#   (id = ticket_id 에서 만든 값)에 들어간다.
#   LangGraph 콜백(CallbackHandler)은 노드 단위 기록이라 LLM 호출 단위인 이 방식으로 충분하다.
#
#   with ticket_scope(ticket_id):
#       graph.invoke(state)
#
#   with trace("classify", "jev-1", prompt, options=options) as span:
#       span.output = call()
#       span.usage = {"input": 120, "output": 8}
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from cs_agent.config import get_settings

_LOGGER = logging.getLogger(__name__)

_ticket_id: ContextVar[str | None] = ContextVar("ticket_id", default=None)


@dataclass
class Span:
    task: str
    model: str
    prompt: str
    output: Any = None
    metadata: dict[str, Any] = field(default_factory=dict)
    usage: dict[str, int] = field(default_factory=dict)  # {"input": 토큰, "output": 토큰}


@lru_cache
def _client() -> Any | None:
    """키가 있으면 Langfuse 클라이언트, 없거나 만들 수 없으면 None (기록 안 함).

    lru_cache 라 실패 경고는 프로세스에서 한 번만 남는다.
    """
    settings = get_settings()
    if not (settings.langfuse_public_key and settings.langfuse_secret_key):
        return None
    try:
        from langfuse import Langfuse
    except ImportError:
        _LOGGER.warning(
            "LANGFUSE 키가 있지만 langfuse 패키지가 없다 → LLM 기록을 건너뛴다 "
            "(설치: uv sync --extra obs)"
        )
        return None
    try:
        return Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_host,
            environment=settings.app_env,
        )
    except Exception as e:
        _LOGGER.warning("Langfuse 클라이언트를 만들지 못했다 → LLM 기록을 건너뛴다: %s", e)
        return None


@contextmanager
def ticket_scope(ticket_id: str) -> Iterator[None]:
    token = _ticket_id.set(ticket_id)
    try:
        yield
    finally:
        _ticket_id.reset(token)


@contextmanager
def trace(task: str, model: str, prompt: str, **metadata: Any) -> Iterator[Span]:
    span = Span(task, model, prompt, metadata=dict(metadata))
    client = _client()
    if client is None:
        yield span
        return

    ticket_id = _ticket_id.get()
    if ticket_id:
        span.metadata.setdefault("ticket_id", ticket_id)
    trace_context = {"trace_id": client.create_trace_id(seed=ticket_id)} if ticket_id else None
    with client.start_as_current_observation(
        trace_context=trace_context,
        name=task,
        as_type="generation",
        model=model,
        input=prompt,
        metadata=span.metadata,
    ) as generation:
        try:
            yield span
        except Exception as e:
            generation.update(level="ERROR", status_message=f"{type(e).__name__}: {e}")
            raise
        finally:
            generation.update(
                output=span.output, usage_details=span.usage or None, metadata=span.metadata
            )


def flush() -> None:
    """앱 종료 시 남은 기록을 보낸다 (main.py lifespan)."""
    client = _client()
    if client is not None:
        client.flush()
