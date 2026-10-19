"""Langfuse 기록 (CSA-48 · 담당 김동규).

모든 LLM 호출을 task 이름·모델 이름과 함께 남긴다. 키가 없으면 아무것도 하지 않는다.
K1(p95 지연)과 Jev·Gemini 비교(9.2)를 여기 기록으로 잰다.
"""

import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from cs_agent.config import get_settings


@dataclass
class Span:
    task: str
    model: str
    prompt: str
    output: Any = None
    metadata: dict[str, Any] = field(default_factory=dict)


@lru_cache
def _client():
    s = get_settings()
    if not (s.langfuse_public_key and s.langfuse_secret_key):
        return None
    from langfuse import Langfuse  # extra: obs

    return Langfuse(
        public_key=s.langfuse_public_key, secret_key=s.langfuse_secret_key, host=s.langfuse_host
    )


@contextmanager
def trace(task: str, model: str, prompt: str, **metadata: Any) -> Iterator[Span]:
    span = Span(task=task, model=model, prompt=prompt, metadata=metadata)
    started = time.perf_counter()
    try:
        yield span
    finally:
        client = _client()
        if client is not None:
            # TODO(CSA-48): ticket_id를 trace id로 묶어 노드 단위로 보이게 한다.
            client.generation(
                name=task,
                model=model,
                input=prompt,
                output=str(span.output),
                metadata={**span.metadata, "latency_s": time.perf_counter() - started},
            )
