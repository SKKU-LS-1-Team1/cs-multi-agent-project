# LLM 모델 분기 (기획서 9.2 · CSA-48 · 담당 김동규 · Sprint 1)
#
# 모든 에이전트는 모델을 직접 부르지 않고 이 라우터를 거친다. 그래야 모델 교체가 설정 한 곳에서
# 되고, 호출이 전부 Langfuse(llm/tracing.py)에 남는다.
#
# | 단계 | 모델 | 메서드 |
# |---|---|---|
# | 문의 분석(유형·제품·긴급) · 필수정보 확인 · 챗봇 의도/재문의/전환 | Jev → 확신도 낮으면 Gemini
#     | judge |
# | 추가정보 요청 · 답변 작성 · 챗봇 답변 | Gemini (writer) | write |
# | 자동 점검 근거 검증 | Gemini (fast) | judge |
# | 규칙·SLA·화면 이동 | 코드 (LLM 안 씀) | - |
#
# - LLM_PROVIDER 가 live 가 아니면 enabled=False: judge 는 첫 보기를 confidence=0 으로, write 는
#   "[LLM 꺼짐] …" 을 돌려준다. 호출한 쪽은 confidence 가 낮으면 규칙 기반 처리로 넘어간다.
# - judge: Jev → confidence < settings.jev_min_confidence 거나 Jev 호출이 실패하면 같은 입력을
#   Gemini(fast)로 다시 판단. JEV_API_KEY·JEV_MODEL 이 비어 있으면 처음부터 Gemini.
#   확신도 기준은 시험 문의로 정한다 (CSA-49).
# - write: Gemini writer 모델로 문장 작성.
# - 호출마다 tracing.trace(task, model, prompt) 로 기록한다. task 이름은 단계 이름(classify,
#   draft, verify_grounding …)으로 통일한다. 대체 호출은 metadata.fallback_from 에 앞 모델이 남는다.
# - TODO(CSA-45): 같은 요청 캐시와 분당 호출 제한 — cache/store.py (cache_key, allow) 가 생기면
#   judge·write 앞에 넣는다.
#
# 완료 기준: 단계별 모델을 .env 만 바꿔서 교체 가능, Langfuse에 task·model·지연 시간이 보임
#
#   llm = get_router()
#   result = llm.judge("classify", prompt, [c.value for c in Category])
#   if result.confidence < 0.5: ...  # 규칙 기반으로
#   text = llm.write("draft", prompt)
from functools import lru_cache

from cs_agent.config import Settings, get_settings
from cs_agent.llm.clients import (
    FakeJudge,
    FakeWriter,
    GeminiClient,
    JevClient,
    Judge,
    Judgement,
    Writer,
)
from cs_agent.llm.tracing import trace


class LLMRouter:
    def __init__(
        self,
        settings: Settings,
        *,
        jev: Judge | None = None,
        gemini_judge: Judge | None = None,
        writer: Writer | None = None,
    ) -> None:
        """클라이언트를 넘기면 그걸 쓴다 (테스트용). 아니면 settings 로 만든다."""
        self.settings = settings
        self.enabled = settings.llm_provider == "live"
        if jev or gemini_judge or writer:
            self.jev, self.gemini_judge = jev, gemini_judge
            self.writer: Writer = writer or FakeWriter()
        elif not self.enabled:
            self.jev, self.gemini_judge, self.writer = FakeJudge(), None, FakeWriter()
        else:
            if not settings.gemini_api_key:
                raise ValueError("LLM_PROVIDER=live 인데 GEMINI_API_KEY 가 비어 있다")
            self.jev = (
                JevClient(settings.jev_api_key, settings.jev_model, settings.jev_base_url)
                if settings.jev_api_key and settings.jev_model
                else None
            )
            self.gemini_judge = GeminiClient(
                settings.gemini_api_key, settings.gemini_model_fast, json_mode=True
            )
            self.writer = GeminiClient(settings.gemini_api_key, settings.gemini_model_writer)

    def _judge_with(self, client: Judge, task: str, prompt: str, options: list[str], **meta):
        with trace(task, client.name, prompt, options=options, **meta) as span:
            result = client.judge(prompt, options)
            span.output = {"answer": result.answer, "confidence": result.confidence}
            span.usage = result.usage
        return result

    def judge(self, task: str, prompt: str, options: list[str]) -> Judgement:
        if not options:
            raise ValueError("options 가 비어 있다")
        first = self.jev or self.gemini_judge
        if first is None:
            raise ValueError("판단 모델이 없다")
        fallback = self.gemini_judge if first is self.jev else None

        try:
            result = self._judge_with(first, task, prompt, options)
        except Exception:
            if fallback is None:
                raise
            return self._judge_with(
                fallback, task, prompt, options, fallback_from=first.name, fallback_reason="error"
            )
        if fallback is None or result.confidence >= self.settings.jev_min_confidence:
            return result
        return self._judge_with(
            fallback,
            task,
            prompt,
            options,
            fallback_from=first.name,
            fallback_reason="low_confidence",
            first_answer=result.answer,
            first_confidence=result.confidence,
        )

    def write(self, task: str, prompt: str) -> str:
        with trace(task, self.writer.name, prompt) as span:
            out = self.writer.write(prompt)
            span.output = out.text
            span.usage = out.usage
        return out.text


@lru_cache
def get_router() -> LLMRouter:
    """앱 전체에서 하나만 쓴다."""
    return LLMRouter(get_settings())
