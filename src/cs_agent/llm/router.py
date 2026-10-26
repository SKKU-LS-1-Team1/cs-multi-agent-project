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
# - write: Gemini writer 모델로 문장 작성. 챗봇 대화(CHAT_TASKS)는 같은 모델을 thinking_level=low 로
#   부른다: 기본 thinking 은 짧은 답에도 수천 토큰을 생각하다 Google 쪽 504(DEADLINE_EXCEEDED)로
#   끝나기도 했다 (2026-10-23 "E.OC 떴어요": 기본 89초 504 / 37초 5,066 토큰, low 4~6초 230 토큰,
#   답 품질 같음). gemini-3.8-flash 는 minimal 을 받지 않는다. 문의 답변 초안은 그대로 둔다.
# - 호출마다 tracing.trace(task, model, prompt) 로 기록한다. task 이름은 단계 이름(classify,
#   draft, verify_grounding …)으로 통일한다. 대체 호출은 metadata.fallback_from 에 앞 모델이 남는다.
# - 같은 요청 캐시·분당 호출 제한 (CSA-45, cache/store.py): kv(Redis 또는 MemoryKV)를 받은
#   라우터만 쓴다. main.py 가 live 일 때 넣는다.
#   - 캐시: judge·write 결과를 llm_cache_ttl_s 동안 재사용. 키 = 단계 + 모델 이름 + (보기)
#     + 프롬프트라서 모델을 바꾸면 새로 부른다. 캐시에서 꺼낸 것도 trace 에 cache_hit=True 로
#     남긴다.
#   - 호출 제한: 모델 호출 직전에 allow("gemini"|"jev", 분당 상한). 넘으면 다음 창까지 기다리되
#     llm_rate_wait_s 를 넘기면 RateLimited — Jev 면 Gemini 로 넘어가고, Gemini 면 호출한 쪽이
#     실패로 처리한다 (분석은 ANALYSIS_PENDING 으로 재시도).
#   - Redis 오류는 캐시 없음·제한 없음으로 보고 그대로 모델을 부른다 (서비스는 멈추지 않는다).
#
# 완료 기준: 단계별 모델을 .env 만 바꿔서 교체 가능, Langfuse에 task·model·지연 시간이 보임
#
#   llm = get_router()
#   result = llm.judge("classify", prompt, [c.value for c in Category])
#   if result.confidence < 0.5: ...  # 규칙 기반으로
#   text = llm.write("draft", prompt)
import json
import logging
import time
from collections.abc import Callable
from dataclasses import asdict
from functools import lru_cache
from typing import Any

from cs_agent.cache.store import allow, cache_key, seconds_to_next_window
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

_LOGGER = logging.getLogger(__name__)

# 챗봇 대화: 짧은 답이라 thinking_level=low 로 부른다 (위 메모)
CHAT_TASKS = frozenset({"chat_answer", "chat_partial", "chat_handoff"})
RATE_WINDOW_S = 60


class RateLimited(RuntimeError):
    """분당 호출 상한에 걸렸고 llm_rate_wait_s 안에 다음 창이 오지 않는다."""


class LLMRouter:
    def __init__(
        self,
        settings: Settings,
        *,
        jev: Judge | None = None,
        gemini_judge: Judge | None = None,
        writer: Writer | None = None,
        kv: Any = None,
        clock: Callable[[], float] = time.time,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        """클라이언트를 넘기면 그걸 쓴다 (테스트용). 아니면 settings 로 만든다.

        kv 를 넘기면 같은 요청 캐시와 분당 호출 제한을 켠다 (cache/store.py).
        """
        self.settings = settings
        self.enabled = settings.llm_provider == "live"
        self.kv = kv
        self._clock, self._sleep = clock, sleep
        if jev or gemini_judge or writer:
            self.jev, self.gemini_judge = jev, gemini_judge
            self.writer: Writer = writer or FakeWriter()
            self.chat_writer: Writer = self.writer
            self.qc_writer: Writer = self.writer
        elif not self.enabled:
            self.jev, self.gemini_judge, self.writer = FakeJudge(), None, FakeWriter()
            self.chat_writer = self.writer
            self.qc_writer = self.writer
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
            self.chat_writer = GeminiClient(
                settings.gemini_api_key, settings.gemini_model_writer, thinking_level="low"
            )

            self.qc_writer = GeminiClient(
                settings.gemini_api_key,
                settings.gemini_model_fast,
                json_mode=True,
                thinking_level="low",
                timeout=20,
                max_retries=0,
            )

    # --- 캐시·호출 제한 (CSA-45) ------------------------------------------------------------

    def _cache_get(self, key: str) -> dict | None:
        if self.kv is None or self.settings.llm_cache_ttl_s <= 0:
            return None
        try:
            raw = self.kv.get(key)
        except Exception as e:
            _LOGGER.warning("LLM 캐시 읽기 실패 → 모델을 부른다: %s", e)
            return None
        return None if raw is None else json.loads(raw)

    def _cache_set(self, key: str, value: dict) -> None:
        if self.kv is None or self.settings.llm_cache_ttl_s <= 0:
            return
        try:
            self.kv.set(
                key, json.dumps(value, ensure_ascii=False), ex=self.settings.llm_cache_ttl_s
            )
        except Exception as e:
            _LOGGER.warning("LLM 캐시 쓰기 실패: %s", e)

    def _bucket(self, client: Any) -> str:
        return "jev" if client is not None and client is self.jev else "gemini"

    def _wait_turn(self, bucket: str) -> None:
        """분당 상한 안이면 바로, 아니면 다음 창까지 기다린다 (llm_rate_wait_s 넘으면 실패)."""
        limit = {"gemini": self.settings.gemini_rpm, "jev": self.settings.jev_rpm}[bucket]
        if self.kv is None or limit <= 0:
            return
        waited = 0.0
        while True:
            now = self._clock()
            try:
                if allow(bucket, limit, RATE_WINDOW_S, kv=self.kv, now=now):
                    return
            except Exception as e:
                _LOGGER.warning("호출 제한 확인 실패 → 제한 없이 부른다: %s", e)
                return
            wait = seconds_to_next_window(RATE_WINDOW_S, now)
            if waited + wait > self.settings.llm_rate_wait_s:
                raise RateLimited(f"{bucket} 분당 {limit}회 초과")
            self._sleep(wait)
            waited += wait

    # --- 판단·작성 ---------------------------------------------------------------------------

    def _judge_with(self, client: Judge, task: str, prompt: str, options: list[str], **meta):
        self._wait_turn(self._bucket(client))
        with trace(task, client.name, prompt, options=options, **meta) as span:
            result = client.judge(prompt, options)
            span.output = {"answer": result.answer, "confidence": result.confidence}
            span.usage = result.usage
        return result

    def judge(self, task: str, prompt: str, options: list[str]) -> Judgement:
        if not options:
            raise ValueError("options 가 비어 있다")
        models = [c.name for c in (self.jev, self.gemini_judge) if c is not None]
        key = cache_key(
            task, json.dumps([models, self.settings.jev_min_confidence, options, prompt])
        )
        if (hit := self._cache_get(key)) is not None:
            result = Judgement(**hit)
            with trace(task, result.model, prompt, options=options, cache_hit=True) as span:
                span.output = {"answer": result.answer, "confidence": result.confidence}
            return result
        result = self._judge(task, prompt, options)
        self._cache_set(key, asdict(result))
        return result

    def _judge(self, task: str, prompt: str, options: list[str]) -> Judgement:
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

    def _writer_for(self, task: str) -> Writer:
        return self.chat_writer if task in CHAT_TASKS else self.writer

    def _write_key(self, task: str, prompt: str) -> str:
        writer = self._writer_for(task)
        level = getattr(writer, "thinking_level", None)
        return cache_key(task, json.dumps([writer.name, prompt] + ([level] if level else [])))

    def invalidate_write(self, task: str, prompt: str) -> None:
        """호출자가 검증에서 거절한 응답을 재시도 때 캐시로 다시 받지 않게 한다."""
        if self.kv is None:
            return
        key = self._write_key(task, prompt)
        try:
            self.kv.expire(key, 0)
        except Exception as e:
            _LOGGER.warning("검증 실패 응답의 캐시 만료 실패: %s", type(e).__name__)

    def write(self, task: str, prompt: str) -> str:
        if task == "customer_send_qc":
            # QC may receive secrets. Neither cache nor tracing stores raw inputs/outputs.
            self._wait_turn("gemini")
            with trace(task, self.qc_writer.name, "[QC input omitted]") as span:
                try:
                    out = self.qc_writer.write(prompt)
                except Exception:
                    raise RuntimeError("Customer QC model call failed") from None
                span.output = "[QC output omitted]"
                span.usage = out.usage
            return out.text
        key = self._write_key(task, prompt)
        if (hit := self._cache_get(key)) is not None:
            with trace(task, hit["model"], prompt, cache_hit=True) as span:
                span.output = hit["text"]
            return hit["text"]
        writer = self._writer_for(task)
        self._wait_turn("gemini")
        with trace(task, writer.name, prompt) as span:
            out = writer.write(prompt)
            span.output = out.text
            span.usage = out.usage
        self._cache_set(key, {"text": out.text, "model": out.model})
        return out.text


@lru_cache
def get_router() -> LLMRouter:
    """앱 전체에서 하나만 쓴다."""
    return LLMRouter(get_settings())
