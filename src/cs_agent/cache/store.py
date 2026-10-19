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
