# Redis 연동 (CSA-45 · 담당 김동규 · Sprint 2)
#
# 세 가지 용도: 같은 요청 캐시, API 호출 제한(Gemini 분당 제한), 챗봇 대화 세션.
#
# 할 일
# 1. get_kv(): settings.redis_url 이 있으면 Redis, 없으면 메모리 구현 (로컬 개발용).
# 2. cache_key(task, prompt): LLM 응답 캐시 키 (task + 프롬프트 해시). llm/router.py 에서 쓴다.
#    캐시 효과 추정: analysis/redis-cache/Redis_캐시_효과_추정.md
# 3. allow(bucket, limit, window_s): 고정 창 호출 제한. 넘으면 False → 라우터가 대기 또는 실패 처리.
# 4. ChatSessionStore: 챗봇 대화 기록을 session_id 별로 TTL(1시간) 동안 보관, 최근 40개까지.
#    문의로 전환되면 PostgreSQL chat_sessions / chat_messages 로 옮긴다 (CSA-24).
#    api/chat.py 가 history() / append() 를 쓴다.
#
# 완료 기준: docker compose 환경에서 챗봇 대화가 API 재시작 후에도 이어짐, 호출 제한 동작 확인
#
# 만들 것 (이름·모양은 다른 파일이 이대로 부른다)
#
#   class ChatSessionStore:
#       """챗봇 대화 기록. 위 '할 일 4' 참고."""
#
#       def history(self, session_id: str) -> list[str]:
#
#       def append(self, session_id: str, *messages: str) -> None:
#
#   def cache_key(task: str, prompt: str) -> str:
#
#   def allow(bucket: str, limit: int, window_s: int = 60) -> bool:
#
# 정해 둔 것
# - Redis 연결은 main.py 가 시작할 때 확인해서 넘긴다 (connect_redis). 연결이 없으면 메모리 구현
#   (MemoryKV) — 서버를 다시 켜면 대화·캐시·호출 횟수가 사라지고, 프로세스끼리 나누지 않는다.
# - LLM 캐시·호출 제한은 llm/router.py 가 judge()·write() 앞에서 쓴다 (kv 를 받은 라우터만).
# - 호출 제한 창은 벽시계(time.time) 기준 고정 창이다. 여러 API 프로세스가 같은 Redis 키를 센다.
import hashlib
import json
import logging
import time
from functools import lru_cache
from typing import Any

SESSION_TTL_S = 3600
SESSION_MAX_MESSAGES = 40

_LOGGER = logging.getLogger(__name__)


class MemoryKV:
    """Redis 대신 쓰는 메모리 저장소. 이 파일과 llm/router.py 가 쓰는 get·set·incr·expire 만."""

    def __init__(self, clock: Any = time.monotonic) -> None:
        self._clock = clock
        self._data: dict[str, tuple[float | None, str]] = {}  # key → (만료 시각, 값)

    def _live(self, key: str) -> tuple[float | None, str] | None:
        item = self._data.get(key)
        if item is not None and item[0] is not None and item[0] <= self._clock():
            del self._data[key]
            return None
        return item

    def get(self, key: str) -> str | None:
        item = self._live(key)
        return None if item is None else item[1]

    def set(self, key: str, value: str, ex: int | None = None) -> bool:
        self._data[key] = (None if ex is None else self._clock() + ex, str(value))
        return True

    def incr(self, key: str) -> int:
        expires, value = self._live(key) or (None, "0")
        count = int(value) + 1
        self._data[key] = (expires, str(count))  # Redis 처럼 만료 시각은 그대로 둔다
        return count

    def expire(self, key: str, seconds: int) -> bool:
        item = self._live(key)
        if item is None:
            return False
        self._data[key] = (self._clock() + seconds, item[1])
        return True


def get_kv(url: str | None = None) -> Any:
    """url(기본 settings.redis_url)에 붙으면 Redis, 비었거나 붙지 않으면 MemoryKV."""
    if url is None:
        from cs_agent.config import get_settings

        url = get_settings().redis_url
    if not url:
        return MemoryKV()
    try:
        return connect_redis(url)
    except Exception as e:
        _LOGGER.warning("Redis 연결 실패 → 메모리 저장소로 대체: %s", e)
        return MemoryKV()


@lru_cache
def _default_kv() -> MemoryKV:
    """kv 를 넘기지 않은 allow() 가 쓰는 프로세스 안 저장소."""
    return MemoryKV()


def cache_key(task: str, prompt: str) -> str:
    """LLM 응답 캐시 키. 같은 단계·같은 프롬프트면 같은 키 (모델·보기는 prompt 에 넣어 넘긴다)."""
    digest = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    return f"llm:{task}:{digest}"


def allow(
    bucket: str,
    limit: int,
    window_s: int = 60,
    *,
    kv: Any = None,
    now: float | None = None,
) -> bool:
    """고정 창 호출 제한. 이번 창(window_s 초)에서 limit 번째 호출까지 True.

    limit ≤ 0 이면 제한 없음. 넘은 호출도 센다 (창이 바뀔 때까지 계속 False).
    """
    if limit <= 0:
        return True
    kv = _default_kv() if kv is None else kv
    now = time.time() if now is None else now
    key = f"rate:{bucket}:{int(now // window_s)}"
    count = int(kv.incr(key))
    if count == 1:
        kv.expire(key, window_s + 1)  # 창이 끝나면 지운다 (1초는 시계 차이 여유)
    return count <= limit


def seconds_to_next_window(window_s: int = 60, now: float | None = None) -> float:
    """allow() 가 False 일 때 다음 창까지 기다릴 시간."""
    now = time.time() if now is None else now
    return window_s - (now % window_s)


def connect_redis(url: str) -> Any:
    """Redis 클라이언트. 붙지 않으면 예외 (main.py 가 메모리로 대체할지 정한다)."""
    import redis

    client = redis.Redis.from_url(url, socket_connect_timeout=3, decode_responses=True)
    client.ping()
    return client


class ChatSessionStore:
    """챗봇 대화 기록. session_id 별로 마지막 대화부터 TTL 동안, 최근 SESSION_MAX_MESSAGES 개."""

    def __init__(
        self,
        client: Any = None,
        ttl_s: int = SESSION_TTL_S,
        max_messages: int = SESSION_MAX_MESSAGES,
        clock: Any = time.monotonic,
    ) -> None:
        self.client = client  # None 이면 메모리
        self.ttl_s = ttl_s
        self.max_messages = max_messages
        self._clock = clock
        self._memory: dict[str, tuple[float, list[str]]] = {}  # session_id → (만료 시각, 기록)

    @staticmethod
    def _key(session_id: str) -> str:
        return f"chat:{session_id}"

    def history(self, session_id: str) -> list[str]:
        if self.client is not None:
            return [json.loads(m) for m in self.client.lrange(self._key(session_id), 0, -1)]
        expires, messages = self._memory.get(session_id, (0.0, []))
        if expires <= self._clock():
            self._memory.pop(session_id, None)
            return []
        return list(messages)

    def append(self, session_id: str, *messages: str) -> None:
        if not messages:
            return
        if self.client is not None:
            key = self._key(session_id)
            pipe = self.client.pipeline()
            pipe.rpush(key, *(json.dumps(m, ensure_ascii=False) for m in messages))
            pipe.ltrim(key, -self.max_messages, -1)
            pipe.expire(key, self.ttl_s)
            pipe.execute()
            return
        kept = (self.history(session_id) + list(messages))[-self.max_messages :]
        self._memory[session_id] = (self._clock() + self.ttl_s, kept)
