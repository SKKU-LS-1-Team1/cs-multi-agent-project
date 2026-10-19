"""Redis 연동 (CSA-45 · 담당 김동규): 같은 요청 캐시, API 호출 제한, 챗봇 대화 세션.

REDIS_URL이 없으면 메모리 구현을 쓴다 (테스트·로컬).
"""

import hashlib
import json
import time
from functools import lru_cache
from typing import Protocol

from cs_agent.config import get_settings


class KV(Protocol):
    def get(self, key: str) -> str | None: ...
    def set(self, key: str, value: str, ex: int | None = None) -> None: ...
    def incr(self, key: str, ex: int) -> int: ...


class MemoryKV:
    def __init__(self) -> None:
        self._data: dict[str, tuple[str, float | None]] = {}

    def get(self, key: str) -> str | None:
        value, expires = self._data.get(key, (None, None))
        if expires is not None and expires < time.time():
            self._data.pop(key, None)
            return None
        return value

    def set(self, key: str, value: str, ex: int | None = None) -> None:
        self._data[key] = (value, time.time() + ex if ex else None)

    def incr(self, key: str, ex: int) -> int:
        n = int(self.get(key) or 0) + 1
        self.set(key, str(n), ex)
        return n


class RedisKV:
    def __init__(self, url: str) -> None:
        import redis

        self._r = redis.Redis.from_url(url, decode_responses=True)

    def get(self, key: str) -> str | None:
        return self._r.get(key)

    def set(self, key: str, value: str, ex: int | None = None) -> None:
        self._r.set(key, value, ex=ex)

    def incr(self, key: str, ex: int) -> int:
        pipe = self._r.pipeline()
        pipe.incr(key)
        pipe.expire(key, ex, nx=True)
        return int(pipe.execute()[0])


@lru_cache
def get_kv() -> KV:
    url = get_settings().redis_url
    return RedisKV(url) if url else MemoryKV()


def cache_key(task: str, prompt: str) -> str:
    return f"llm:{task}:{hashlib.sha256(prompt.encode()).hexdigest()[:32]}"


def allow(bucket: str, limit: int, window_s: int = 60, kv: KV | None = None) -> bool:
    """고정 창 호출 제한. Gemini 분당 호출 제한 등에 쓴다."""
    kv = kv or get_kv()
    window = int(time.time() // window_s)
    return kv.incr(f"rate:{bucket}:{window}", window_s) <= limit


class ChatSessionStore:
    """챗봇 대화 기록. TTL 동안만 Redis에 두고, 문의 전환 시 PostgreSQL로 옮긴다."""

    def __init__(self, kv: KV | None = None, ttl_s: int = 3600) -> None:
        self.kv = kv or get_kv()
        self.ttl_s = ttl_s

    def history(self, session_id: str) -> list[str]:
        return json.loads(self.kv.get(f"chat:{session_id}") or "[]")

    def append(self, session_id: str, *messages: str) -> None:
        history = self.history(session_id) + list(messages)
        self.kv.set(f"chat:{session_id}", json.dumps(history[-40:]), ex=self.ttl_s)
