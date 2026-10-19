"""단계별 모델 분기 (기획서 9.2).

| 단계 | 모델 |
|---|---|
| 문의 분석(유형·제품·긴급) · 필수정보 확인 · 챗봇 의도/재문의/전환 | Jev → 확신도 낮으면 Gemini |
| 추가정보 요청 · 답변 작성 · 챗봇 답변 | Gemini (writer) |
| 자동 점검 근거 검증 | Gemini (fast) |

`llm_provider=fake`이면 `enabled`가 False이고, 각 에이전트는 코드 규칙으로 동작한다.
"""

from functools import lru_cache

from cs_agent.config import Settings, get_settings
from cs_agent.llm.clients import GeminiClient, JevClient, Judgement
from cs_agent.llm.tracing import trace


class LLMRouter:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.enabled = settings.llm_provider == "live"
        self._jev: JevClient | None = None
        self._fast: GeminiClient | None = None
        self._writer: GeminiClient | None = None
        if self.enabled:
            if settings.jev_api_key:
                self._jev = JevClient(
                    settings.jev_api_key, settings.jev_base_url, settings.jev_model
                )
            if settings.gemini_api_key:
                self._fast = GeminiClient(settings.gemini_api_key, settings.gemini_model_fast)
                self._writer = GeminiClient(settings.gemini_api_key, settings.gemini_model_writer)

    def judge(self, task: str, prompt: str, options: list[str]) -> Judgement:
        """Jev로 판단하고, 확신도가 기준보다 낮으면 같은 입력을 Gemini로 다시 판단한다."""
        if self._jev is not None:
            with trace(task, model=self._jev.name, prompt=prompt) as t:
                result = self._jev.judge(prompt, options)
                t.output = result
            if result.confidence >= self.settings.jev_min_confidence or self._fast is None:
                return result
        if self._fast is None:
            raise RuntimeError("LLM이 설정되지 않았다 (GEMINI_API_KEY / JEV_API_KEY)")
        with trace(task, model=self._fast.name, prompt=prompt) as t:
            result = self._fast.judge(prompt, options)
            t.output = result
        return result

    def write(self, task: str, prompt: str) -> str:
        if self._writer is None:
            raise RuntimeError("Gemini가 설정되지 않았다 (GEMINI_API_KEY)")
        with trace(task, model=self._writer.name, prompt=prompt) as t:
            text = self._writer.write(prompt)
            t.output = text
        return text


@lru_cache
def get_router() -> LLMRouter:
    return LLMRouter(get_settings())
