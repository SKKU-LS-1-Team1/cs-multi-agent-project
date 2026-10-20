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
# 지금 들어간 것: 할 일 4 (ChatSessionStore). Redis 연결은 main.py 가 시작할 때 확인해서 넘긴다
#   (connect_redis). 연결이 없으면 메모리 구현 — 서버를 다시 켜면 대화가 사라진다.
# TODO(CSA-45): 1 get_kv · 2 cache_key · 3 allow (LLM 캐시·호출 제한, llm/router.py 연결)
import json
import time
from typing import Any

SESSION_TTL_S = 3600
SESSION_MAX_MESSAGES = 40


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
