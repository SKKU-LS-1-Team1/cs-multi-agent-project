"""모델별 클라이언트.

- Jev: 판단 전용. 정해진 보기 중 하나와 확신도를 돌려준다. DigitalOcean 서버리스 추론 API.
- Gemini: 고객에게 나갈 문장 작성, 값 추출, 근거 검증.
"""

import json
from dataclasses import dataclass
from typing import Protocol

import httpx


@dataclass
class Judgement:
    answer: str
    confidence: float
    model: str


class Judge(Protocol):
    name: str

    def judge(self, prompt: str, options: list[str]) -> Judgement: ...


class Writer(Protocol):
    name: str

    def write(self, prompt: str) -> str: ...


class JevClient:
    """TODO(CSA-26): 실제 요청·응답 형식은 얼리 액세스 문서 기준으로 맞춘다."""

    def __init__(self, api_key: str, base_url: str, model: str) -> None:
        self.name = model
        self._http = httpx.Client(
            base_url=base_url, headers={"Authorization": f"Bearer {api_key}"}, timeout=10
        )

    def judge(self, prompt: str, options: list[str]) -> Judgement:
        resp = self._http.post(
            "/chat/completions",
            json={
                "model": self.name,
                "messages": [{"role": "user", "content": prompt}],
                "response_format": {"type": "json_object"},
                "extra_body": {"choices": options},
            },
        )
        resp.raise_for_status()
        content = json.loads(resp.json()["choices"][0]["message"]["content"])
        return Judgement(content["answer"], float(content.get("confidence", 0.0)), self.name)


class GeminiClient:
    def __init__(self, api_key: str, model: str) -> None:
        from langchain_google_genai import ChatGoogleGenerativeAI  # extra: llm

        self.name = model
        self._chat = ChatGoogleGenerativeAI(model=model, google_api_key=api_key)

    def write(self, prompt: str) -> str:
        return str(self._chat.invoke(prompt).content)

    def judge(self, prompt: str, options: list[str]) -> Judgement:
        text = self.write(
            f"{prompt}\n\n다음 보기 중 하나만 JSON으로 답하라: "
            f'{{"answer": <{"|".join(options)}>, "confidence": 0~1}}'
        )
        data = json.loads(text.strip().removeprefix("```json").removesuffix("```"))
        return Judgement(data["answer"], float(data.get("confidence", 0.0)), self.name)
