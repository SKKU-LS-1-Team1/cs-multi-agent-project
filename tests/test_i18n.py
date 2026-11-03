import json

import pytest
from fastapi.testclient import TestClient

from cs_agent.cache.store import MemoryKV
from cs_agent.config import Settings
from cs_agent.llm.clients import Completion
from cs_agent.llm.router import LLMRouter
from cs_agent.main import create_app


class ListWriter:
    """프롬프트에 든 문구 배열을 받아 '[lang] 문구' 로 돌려준다."""

    name = "gemini-writer"

    def __init__(self, broken=False):
        self.prompts: list[str] = []
        self.broken = broken

    def write(self, prompt):
        self.prompts.append(prompt)
        texts = json.loads(prompt.rsplit("Input:\n", 1)[1])
        if self.broken:
            return Completion("[]", self.name)
        return Completion(
            "```json\n" + json.dumps([f"[ja] {t}" for t in texts]) + "\n```", self.name
        )


def _client(writer):
    llm = LLMRouter(
        Settings(_env_file=None, llm_provider="live", gemini_api_key="x"), writer=writer
    )
    llm.kv = MemoryKV()
    return TestClient(create_app(llm=llm, storage="memory", retrievers=(None, None)))


@pytest.fixture
def writer():
    return ListWriter()


def test_translates_and_caches_each_text(writer):
    with _client(writer) as c:
        r = c.post("/api/i18n/translate", json={"lang": "ja", "texts": ["문의 남기기", "내 문의"]})
        assert r.status_code == 200
        assert r.json() == {"lang": "ja", "translations": ["[ja] 문의 남기기", "[ja] 내 문의"]}
        # 하나는 캐시, 새 문구만 모델로 간다
        r = c.post("/api/i18n/translate", json={"lang": "ja", "texts": ["내 문의", "보내기"]})
        assert r.json()["translations"] == ["[ja] 내 문의", "[ja] 보내기"]
    assert len(writer.prompts) == 2
    assert "내 문의" not in writer.prompts[1]
    assert "Japanese" in writer.prompts[0]


def test_korean_returns_original_without_model(writer):
    with _client(writer) as c:
        r = c.post("/api/i18n/translate", json={"lang": "ko", "texts": ["보내기"]})
    assert r.json()["translations"] == ["보내기"]
    assert writer.prompts == []


def test_unsupported_language_is_rejected(writer):
    with _client(writer) as c:
        assert (
            c.post("/api/i18n/translate", json={"lang": "xx", "texts": ["보내기"]}).status_code
            == 422
        )


def test_bad_model_output_falls_back_to_original_and_is_not_cached():
    w = ListWriter(broken=True)
    with _client(w) as c:
        r = c.post("/api/i18n/translate", json={"lang": "ja", "texts": ["보내기"]})
        assert r.json()["translations"] == ["보내기"]
        c.post("/api/i18n/translate", json={"lang": "ja", "texts": ["보내기"]})
    assert len(w.prompts) == 2  # 캐시하지 않아 다시 시도한다


def test_llm_off_returns_original():
    with TestClient(
        create_app(
            llm=LLMRouter(Settings(_env_file=None)), storage="memory", retrievers=(None, None)
        )
    ) as c:
        r = c.post("/api/i18n/translate", json={"lang": "en", "texts": ["보내기"]})
    assert r.json()["translations"] == ["보내기"]
