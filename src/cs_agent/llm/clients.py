# 모델별 클라이언트 (CSA-48 · 담당 김동규)
#
# 라우터(llm/router.py)만 이 파일을 쓴다. 에이전트는 라우터의 judge()/write() 를 부른다.
#
# - JevClient: TypeSafe AI의 판단 전용 모델 (https://docs.typesafe.ai/api).
#   POST {jev_base_url}/systemone 에 state(판단할 글)와 choice 질문(criteria = 보기)을 보내면
#   choice(고른 보기)·probabilities(보기별 확률)·confidence(0~1)를 돌려준다. 글을 생성하지 않는다.
#   jev-latest 는 별칭이고 실제 버전(예: jev-1.13.0)은 응답 model 에 온다 → Judgement.model.
# - GeminiClient: langchain-google-genai 의 ChatGoogleGenerativeAI (extra: llm).
#   write() = 문장 작성, judge() = 보기 중 하나를 JSON 으로 받기 (Jev 대체용).
# - FakeJudge / FakeWriter: LLM_PROVIDER 가 live 가 아닐 때 (키 없이 개발·CI).
#
# 타임아웃·재시도 (지연 목표 K1 p95 ≤ 60초)
# - Jev: 요청당 20초, 429·529(과부하)·5xx·연결 오류는 최대 3번 시도
#   (0.5초→1초, Retry-After 는 5초까지 따름)
# - Gemini: 판단 20초, 작성 45초, langchain 기본 재시도 2번
#
# 판단 결과가 보기에 없거나 (Gemini 는) JSON 이 아니면 confidence=0 으로 돌려준다.
# 라우터는 이를 확신도 낮음으로 보고 다음 모델로 넘긴다.
import json
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

JEV_TIMEOUT_S = 20.0
JEV_MAX_ATTEMPTS = 3
GEMINI_JUDGE_TIMEOUT_S = 20.0
GEMINI_WRITE_TIMEOUT_S = 45.0
GEMINI_MAX_RETRIES = 2
RETRY_STATUS = {429, 500, 502, 503, 504, 529}
JEV_QUESTION = "answer"
JEV_INSTRUCTIONS = "Answer the request in the state by choosing exactly one option."


@dataclass
class Judgement:
    answer: str  # options 중 하나
    confidence: float  # 0~1
    model: str
    usage: dict[str, int] = field(default_factory=dict)  # {"input": 토큰, "output": 토큰}


@dataclass
class Completion:
    text: str
    model: str
    usage: dict[str, int] = field(default_factory=dict)


class Judge(Protocol):
    name: str

    def judge(self, prompt: str, options: list[str]) -> Judgement: ...


class Writer(Protocol):
    name: str

    def write(self, prompt: str) -> Completion: ...


def judge_prompt(prompt: str, options: list[str]) -> str:
    choices = "\n".join(f"- {o}" for o in options)
    return (
        f"{prompt}\n\n"
        f"Choose exactly one of these options:\n{choices}\n\n"
        'Reply with JSON only: {"answer": "<one option>", "confidence": <0.0-1.0>}'
    )


_JSON_OBJECT = re.compile(r"\{.*\}", re.S)


def parse_judgement(text: str, options: list[str], model: str) -> Judgement:
    """모델 응답 글 → Judgement. 보기에 없거나 형식이 틀리면 confidence=0."""
    by_lower = {o.lower(): o for o in options}
    try:
        data = json.loads(_JSON_OBJECT.search(text or "").group(0))  # type: ignore[union-attr]
        answer = by_lower[str(data["answer"]).strip().lower()]
        confidence = min(max(float(data.get("confidence", 0.0)), 0.0), 1.0)
    except (AttributeError, KeyError, TypeError, ValueError):
        return Judgement(options[0], 0.0, model)
    return Judgement(answer, confidence, model)


class JevClient:
    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str,
        *,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.name = model
        self._sleep = sleep
        self._http = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=JEV_TIMEOUT_S,
            transport=transport,
        )

    def _request(self, prompt: str, options: list[str]) -> dict[str, Any]:
        body = {
            "model": self.name,
            "state": prompt,
            "questions": {
                JEV_QUESTION: {
                    "type": "choice",
                    "instructions": JEV_INSTRUCTIONS,
                    "criteria": {o: None for o in options},
                }
            },
        }
        for attempt in range(1, JEV_MAX_ATTEMPTS + 1):
            try:
                res = self._http.post("/systemone", json=body)
            except httpx.TransportError:
                if attempt == JEV_MAX_ATTEMPTS:
                    raise
                self._sleep(0.5 * 2 ** (attempt - 1))
                continue
            if res.status_code in RETRY_STATUS and attempt < JEV_MAX_ATTEMPTS:
                retry_after = res.headers.get("retry-after", "")
                wait = float(retry_after) if retry_after.isdigit() else 0.5 * 2 ** (attempt - 1)
                self._sleep(min(wait, 5.0))
                continue
            res.raise_for_status()
            return res.json()
        raise AssertionError("unreachable")

    def judge(self, prompt: str, options: list[str]) -> Judgement:
        data = self._request(prompt, options)
        answer = data["answers"][JEV_QUESTION]
        usage = data.get("usage") or {}
        choice = answer.get("choice")
        return Judgement(
            choice if choice in options else options[0],
            float(answer.get("confidence", 0.0)) if choice in options else 0.0,
            data.get("model", self.name),
            {
                "input": int(usage.get("input_tokens", 0)),
                "output": int(usage.get("output_tokens", 0)),
            },
        )


class GeminiClient:
    def __init__(
        self,
        api_key: str,
        model: str,
        *,
        json_mode: bool = False,
        thinking_level: str | None = None,
    ) -> None:
        from langchain_google_genai import ChatGoogleGenerativeAI

        self.name = model
        self.thinking_level = thinking_level
        extra = {"thinking_level": thinking_level} if thinking_level else {}
        self._chat = ChatGoogleGenerativeAI(
            model=model,
            google_api_key=api_key,
            temperature=0 if json_mode else 0.3,
            timeout=GEMINI_JUDGE_TIMEOUT_S if json_mode else GEMINI_WRITE_TIMEOUT_S,
            max_retries=GEMINI_MAX_RETRIES,
            response_mime_type="application/json" if json_mode else None,
            **extra,
        )

    def _invoke(self, prompt: str) -> Completion:
        msg = self._chat.invoke(prompt)
        meta = msg.usage_metadata or {}
        usage = {"input": meta.get("input_tokens", 0), "output": meta.get("output_tokens", 0)}
        return Completion(msg.text, self.name, usage)

    def write(self, prompt: str) -> Completion:
        return self._invoke(prompt)

    def judge(self, prompt: str, options: list[str]) -> Judgement:
        out = self._invoke(judge_prompt(prompt, options))
        result = parse_judgement(out.text, options, self.name)
        result.usage = out.usage
        return result


class FakeJudge:
    """LLM 을 끈 상태. 첫 보기를 confidence=0 으로 돌려준다 (호출한 쪽은 규칙 기반으로 처리)."""

    name = "fake"

    def judge(self, prompt: str, options: list[str]) -> Judgement:
        return Judgement(options[0], 0.0, self.name)


class FakeWriter:
    """LLM 을 끈 상태. 프롬프트 앞부분을 그대로 돌려준다 (흐름 확인용)."""

    name = "fake"

    def write(self, prompt: str) -> Completion:
        return Completion(f"[LLM 꺼짐] {prompt[:200]}", self.name)
