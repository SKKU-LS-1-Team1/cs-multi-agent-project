# LLM 모델 분기 (기획서 9.2 · CSA-48 · 담당 김동규 · Sprint 1)
#
# 모든 에이전트는 모델을 직접 부르지 않고 이 라우터를 거친다. 그래야 모델 교체가 설정 한 곳에서
#   되고,
# 호출이 전부 Langfuse(llm/tracing.py)에 남는다.
#
# | 단계 | 모델 | 메서드 |
# |---|---|---|
# | 문의 분석(유형·제품·긴급) · 필수정보 확인 · 챗봇 의도/재문의/전환 | Jev → 확신도 낮으면 Gemini
#     | judge |
# | 추가정보 요청 · 답변 작성 · 챗봇 답변 | Gemini (writer) | write |
# | 자동 점검 근거 검증 | Gemini (fast) | judge |
# | 규칙·SLA·화면 이동 | 코드 (LLM 안 씀) | - |
#
# 할 일
# 1. __init__: settings 의 키로 Jev·Gemini 클라이언트(llm/clients.py)를 만든다.
#    settings.llm_provider 가 "live" 가 아니면 enabled=False (키 없이 개발할 때).
# 2. judge(task, prompt, options): Jev로 판단 → confidence < settings.jev_min_confidence 면 같은
#    입력을 Gemini로 다시 판단. 확신도 기준은 시험 문의로 정한다 (CSA-49).
# 3. write(task, prompt): Gemini writer 모델로 문장 작성.
# 4. 둘 다 tracing.trace(task, model, prompt) 로 감싸 기록한다. task 이름은 단계 이름(classify,
#    draft, verify_grounding …)으로 통일한다.
# 5. 같은 요청 캐시와 분당 호출 제한은 cache/store.py (cache_key, allow) 를 쓴다 (CSA-45).
#
# 완료 기준: 단계별 모델을 .env 만 바꿔서 교체 가능, Langfuse에 task·model·지연 시간이 보임
#
# 만들 것 (이름·모양은 다른 파일이 이대로 부른다)
#
#   class LLMRouter:
#       def __init__(self, settings: Settings) -> None:
#           self.settings = settings
#           self.enabled = settings.llm_provider == "live"
#
#       def judge(self, task: str, prompt: str, options: list[str]) -> Judgement:
#
#       def write(self, task: str, prompt: str) -> str:
#
#   def get_router() -> LLMRouter:
#       """앱 전체에서 하나만 쓴다 (lru_cache)."""
