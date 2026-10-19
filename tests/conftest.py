import pytest

from cs_agent.llm import tracing


@pytest.fixture(autouse=True)
def _no_langfuse(monkeypatch):
    """로컬 .env 에 Langfuse 키가 있어도 테스트는 기록을 보내지 않는다."""
    monkeypatch.setattr(tracing, "_client", lambda: None)
