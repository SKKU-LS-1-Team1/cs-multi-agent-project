import json
from contextlib import contextmanager

import httpx
import pytest

from cs_agent.cache.store import MemoryKV
from cs_agent.config import Settings
from cs_agent.llm import tracing
from cs_agent.llm.clients import Completion, JevClient, Judgement, parse_judgement
from cs_agent.llm.router import LLMRouter, RateLimited

OPTIONS = ["DEFECT", "RETURN", "QUOTE"]


class StubJudge:
    def __init__(self, name, answer="RETURN", confidence=0.9, error=None):
        self.name, self.answer, self.confidence, self.error = name, answer, confidence, error
        self.calls = 0

    def judge(self, prompt, options):
        self.calls += 1
        if self.error:
            raise self.error
        return Judgement(self.answer, self.confidence, self.name, {"input": 10, "output": 2})


class StubWriter:
    name = "gemini-writer"

    def __init__(self):
        self.calls = 0

    def write(self, prompt):
        self.calls += 1
        return Completion(f"답변: {prompt}", self.name, {"input": 5, "output": 7})


def settings(**kw) -> Settings:
    return Settings(_env_file=None, **kw)


# --- router -------------------------------------------------------------------------------


def test_disabled_router_needs_no_keys():
    router = LLMRouter(settings(llm_provider="fake"))

    assert router.enabled is False
    result = router.judge("classify", "문의", OPTIONS)
    assert (result.answer, result.confidence, result.model) == ("DEFECT", 0.0, "fake")
    assert router.write("draft", "안녕하세요").startswith("[LLM 꺼짐]")


def test_live_router_requires_gemini_key():
    with pytest.raises(ValueError, match="GEMINI_API_KEY"):
        LLMRouter(settings(llm_provider="live"))


def test_confident_jev_answer_is_used():
    jev, gemini = StubJudge("jev", confidence=0.9), StubJudge("gemini-fast", answer="QUOTE")
    router = LLMRouter(settings(jev_min_confidence=0.7), jev=jev, gemini_judge=gemini)

    result = router.judge("classify", "문의", OPTIONS)

    assert (result.answer, result.model) == ("RETURN", "jev")
    assert gemini.calls == 0


def test_low_confidence_falls_back_to_gemini():
    jev, gemini = StubJudge("jev", confidence=0.4), StubJudge("gemini-fast", answer="QUOTE")
    router = LLMRouter(settings(jev_min_confidence=0.7), jev=jev, gemini_judge=gemini)

    result = router.judge("classify", "문의", OPTIONS)

    assert (result.answer, result.model) == ("QUOTE", "gemini-fast")
    assert jev.calls == gemini.calls == 1


def test_jev_error_falls_back_to_gemini():
    jev = StubJudge("jev", error=httpx.ConnectError("down"))
    gemini = StubJudge("gemini-fast", answer="QUOTE")
    router = LLMRouter(settings(), jev=jev, gemini_judge=gemini)

    assert router.judge("classify", "문의", OPTIONS).model == "gemini-fast"


def test_without_jev_gemini_judges_directly():
    gemini = StubJudge("gemini-fast", confidence=0.1)
    router = LLMRouter(settings(), gemini_judge=gemini)

    result = router.judge("verify_grounding", "근거", ["yes", "no"])

    assert result.model == "gemini-fast"  # 대체할 모델이 없으면 확신도가 낮아도 그대로
    assert gemini.calls == 1


def test_write_uses_writer():
    router = LLMRouter(settings(), writer=StubWriter())

    assert router.write("draft", "문의 요약") == "답변: 문의 요약"


def test_chat_tasks_use_the_low_thinking_writer(monkeypatch):
    # 기본 thinking 은 짧은 챗봇 답에도 수천 토큰을 생각하다 504 로 끝났다 (router.py 메모)
    from cs_agent.llm import router as router_module

    made = []

    class Gemini(StubWriter):
        def __init__(
            self,
            api_key,
            model,
            *,
            json_mode=False,
            thinking_level=None,
            timeout=None,
            max_retries=2,
        ):
            super().__init__()
            self.json_mode, self.thinking_level = json_mode, thinking_level
            made.append(self)

    monkeypatch.setattr(router_module, "GeminiClient", Gemini)
    router = LLMRouter(settings(llm_provider="live", gemini_api_key="k"), kv=MemoryKV())
    for task in ("chat_answer", "chat_partial", "chat_handoff", "draft"):
        router.write(task, "p")

    chat = next(m for m in made if m.thinking_level == "low")
    draft = next(m for m in made if not m.json_mode and m.thinking_level is None)
    assert (chat.calls, draft.calls) == (3, 1)  # 답변 초안은 기본 thinking 그대로

    router.invalidate_write("chat_handoff", "p")  # 같은 키를 지운다 → 다시 부른다
    router.write("chat_handoff", "p")
    assert chat.calls == 4


# --- clients ------------------------------------------------------------------------------


# --- 캐시·호출 제한 (CSA-45) -------------------------------------------------------------


class FakeTime:
    def __init__(self, now=0.0):
        self.now = now
        self.slept = []

    def clock(self):
        return self.now

    def sleep(self, seconds):
        self.slept.append(seconds)
        self.now += seconds


def test_cache_reuses_judge_and_write_results():
    jev, writer = StubJudge("jev"), StubWriter()
    router = LLMRouter(settings(), jev=jev, writer=writer, kv=MemoryKV())

    first = router.judge("classify", "p", OPTIONS)
    again = router.judge("classify", "p", OPTIONS)
    router.judge("classify", "p", ["RETURN", "QUOTE"])  # 보기가 다르면 새로
    router.judge("detect_language", "p", OPTIONS)  # 단계가 다르면 새로

    assert again == first and jev.calls == 3
    assert router.write("draft", "q") == router.write("draft", "q") and writer.calls == 1


def test_no_cache_without_kv_or_when_ttl_zero():
    jev = StubJudge("jev")
    LLMRouter(settings(), jev=jev).judge("classify", "p", OPTIONS)
    router = LLMRouter(settings(llm_cache_ttl_s=0), jev=jev, kv=MemoryKV())
    router.judge("classify", "p", OPTIONS)
    router.judge("classify", "p", OPTIONS)
    assert jev.calls == 3


def test_cache_errors_do_not_block_calls():
    class BrokenKV:
        def _down(self, *args, **kwargs):
            raise ConnectionError("redis down")

        get = set = incr = expire = _down

    jev = StubJudge("jev")
    router = LLMRouter(settings(jev_rpm=1), jev=jev, kv=BrokenKV())
    assert router.judge("classify", "p", OPTIONS).answer == "RETURN"
    assert router.judge("classify", "p", OPTIONS).answer == "RETURN"
    assert jev.calls == 2


def test_rate_limit_waits_for_next_window():
    t = FakeTime(now=50.0)
    writer = StubWriter()
    router = LLMRouter(
        settings(gemini_rpm=1, llm_rate_wait_s=20, llm_cache_ttl_s=0),
        writer=writer,
        kv=MemoryKV(),
        clock=t.clock,
        sleep=t.sleep,
    )

    router.write("draft", "a")
    router.write("draft", "b")  # 이번 창은 다 썼다 → 10초 기다려 다음 창

    assert t.slept == [10.0] and writer.calls == 2


def test_rate_limit_fails_when_wait_too_long_and_jev_falls_back():
    t = FakeTime(now=0.0)
    jev, gemini = StubJudge("jev"), StubJudge("gemini")
    router = LLMRouter(
        settings(jev_rpm=1, gemini_rpm=1, llm_rate_wait_s=20, llm_cache_ttl_s=0),
        jev=jev,
        gemini_judge=gemini,
        kv=MemoryKV(),
        clock=t.clock,
        sleep=t.sleep,
    )

    assert router.judge("classify", "a", OPTIONS).model == "jev"
    # Jev 상한 초과(60초 대기 필요) → Gemini 로
    assert router.judge("classify", "b", OPTIONS).model == "gemini"
    with pytest.raises(RateLimited):  # Gemini 도 초과 → 실패
        router.judge("classify", "c", OPTIONS)
    assert t.slept == [] and (jev.calls, gemini.calls) == (1, 1)


@pytest.mark.parametrize(
    ("text", "answer", "confidence"),
    [
        ('{"answer": "RETURN", "confidence": 0.82}', "RETURN", 0.82),
        ('```json\n{"answer": "quote", "confidence": 1.5}\n```', "QUOTE", 1.0),
        ('{"answer": "OTHER", "confidence": 0.9}', "DEFECT", 0.0),  # 보기에 없음
        ("RETURN 입니다", "DEFECT", 0.0),  # JSON 아님
    ],
)
def test_parse_judgement(text, answer, confidence):
    result = parse_judgement(text, OPTIONS, "m")

    assert (result.answer, result.confidence) == (answer, confidence)


def _jev_response(choice: str, confidence: float) -> httpx.Response:
    # https://docs.typesafe.ai/api 의 choice 응답 형식
    return httpx.Response(
        200,
        json={
            "model": "jev-1.13.0",
            "answers": {
                "answer": {
                    "type": "choice",
                    "choice": choice,
                    "confidence": confidence,
                    "probabilities": {o: (confidence if o == choice else 0.0) for o in OPTIONS},
                }
            },
            "usage": {"input_tokens": 325, "output_tokens": 48},
        },
    )


def test_jev_client_retries_429_then_parses():
    requests, waits = [], []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(429, headers={"retry-after": "2"})
        return _jev_response("RETURN", 0.77)

    jev = JevClient(
        "key",
        "jev-1",
        "https://jev.test/v1",
        transport=httpx.MockTransport(handler),
        sleep=waits.append,
    )

    result = jev.judge("문의", OPTIONS)

    assert (result.answer, result.confidence, result.model) == ("RETURN", 0.77, "jev-1.13.0")
    assert result.usage == {"input": 325, "output": 48}
    assert waits == [2.0]
    sent = requests[-1]
    assert sent.url == "https://jev.test/v1/systemone"
    assert sent.headers["authorization"] == "Bearer key"
    body = json.loads(sent.content)
    assert body["model"] == "jev-1"
    assert body["state"] == "문의"
    assert body["questions"]["answer"]["type"] == "choice"
    assert body["questions"]["answer"]["criteria"] == {o: None for o in OPTIONS}


def test_jev_choice_outside_options_has_zero_confidence():
    jev = JevClient(
        "key",
        "jev-1",
        "https://jev.test/v1",
        transport=httpx.MockTransport(lambda r: _jev_response("OTHER", 0.9)),
    )

    result = jev.judge("문의", OPTIONS)

    assert (result.answer, result.confidence) == ("DEFECT", 0.0)


def test_jev_client_gives_up_after_max_attempts():
    jev = JevClient(
        "key",
        "jev-1",
        "https://jev.test/v1",
        transport=httpx.MockTransport(lambda r: httpx.Response(529)),
        sleep=lambda s: None,
    )

    with pytest.raises(httpx.HTTPStatusError):
        jev.judge("문의", OPTIONS)


# --- tracing ------------------------------------------------------------------------------


class FakeGeneration:
    def __init__(self, kwargs):
        self.start = kwargs
        self.updates: dict = {}

    def update(self, **kw):
        self.updates.update(kw)


class FakeLangfuse:
    def __init__(self):
        self.generations: list[FakeGeneration] = []

    def create_trace_id(self, seed=None):
        return f"trace-{seed}"

    @contextmanager
    def start_as_current_observation(self, **kwargs):
        generation = FakeGeneration(kwargs)
        self.generations.append(generation)
        yield generation


@pytest.fixture
def langfuse(monkeypatch):
    fake = FakeLangfuse()
    monkeypatch.setattr(tracing, "_client", lambda: fake)
    return fake


def test_trace_is_noop_without_keys(monkeypatch):
    monkeypatch.setattr(tracing, "_client", lambda: None)

    with tracing.trace("draft", "m", "p") as span:
        span.output = "x"

    assert span.output == "x"


# conftest 가 모든 테스트에서 _client 를 "기록 안 함"으로 바꾸므로, 실제 함수는 불러올 때 잡아 둔다
_REAL_CLIENT = tracing._client


@pytest.fixture
def langfuse_keys(monkeypatch):
    """키가 있는 설정 + 실제 _client() (lru_cache 를 비우고, 끝나면 다시 비운다)."""
    monkeypatch.setattr(
        tracing,
        "get_settings",
        lambda: settings(langfuse_public_key="pk", langfuse_secret_key="sk"),
    )
    monkeypatch.setattr(tracing, "_client", _REAL_CLIENT)
    _REAL_CLIENT.cache_clear()
    yield
    _REAL_CLIENT.cache_clear()


def test_missing_langfuse_package_skips_tracing_not_llm_calls(langfuse_keys, monkeypatch, caplog):
    """키는 있는데 langfuse 가 설치 안 됐으면 기록만 건너뛴다 — 판단·작성은 그대로 (PR #31)."""
    import sys

    monkeypatch.setitem(sys.modules, "langfuse", None)  # import langfuse → ImportError

    router = LLMRouter(settings(), jev=StubJudge("jev"), writer=StubWriter())
    assert router.judge("classify", "p", OPTIONS).answer == "RETURN"
    assert router.write("draft", "q") == "답변: q"
    assert tracing._client() is None
    tracing.flush()  # 종료 때도 문제없다
    assert sum("langfuse 패키지가 없다" in r.message for r in caplog.records) == 1  # 경고는 한 번


def test_langfuse_client_error_skips_tracing(langfuse_keys, monkeypatch):
    import sys
    import types

    def broken(**kwargs):
        raise ValueError("bad host")

    monkeypatch.setitem(sys.modules, "langfuse", types.SimpleNamespace(Langfuse=broken))

    with tracing.trace("draft", "m", "p") as span:
        span.output = "x"
    assert span.output == "x" and tracing._client() is None


def test_router_calls_are_traced_under_ticket(langfuse):
    jev, gemini = StubJudge("jev", confidence=0.4), StubJudge("gemini-fast", answer="QUOTE")
    router = LLMRouter(settings(), jev=jev, gemini_judge=gemini, writer=StubWriter())

    with tracing.ticket_scope("T-1"):
        router.judge("classify", "문의", OPTIONS)
        router.write("draft", "요약")

    first, fallback, draft = langfuse.generations
    assert [g.start["name"] for g in langfuse.generations] == ["classify", "classify", "draft"]
    assert [g.start["model"] for g in langfuse.generations] == [
        "jev",
        "gemini-fast",
        "gemini-writer",
    ]
    assert {g.start["trace_context"]["trace_id"] for g in langfuse.generations} == {"trace-T-1"}
    assert first.updates["output"] == {"answer": "RETURN", "confidence": 0.4}
    assert first.updates["usage_details"] == {"input": 10, "output": 2}
    assert fallback.start["metadata"]["fallback_from"] == "jev"
    assert fallback.start["metadata"]["fallback_reason"] == "low_confidence"
    assert draft.updates["output"] == "답변: 요약"


def test_trace_marks_errors(langfuse):
    with pytest.raises(RuntimeError), tracing.trace("draft", "m", "p"):
        raise RuntimeError("boom")

    (generation,) = langfuse.generations
    assert generation.start["trace_context"] is None  # 문의 밖 호출은 trace 를 따로
    assert generation.updates["level"] == "ERROR"
