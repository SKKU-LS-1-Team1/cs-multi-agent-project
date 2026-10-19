import pytest

from cs_agent.agents.retrieval import KeywordRetriever
from cs_agent.config import Settings
from cs_agent.graph.builder import GraphDeps
from cs_agent.llm.router import LLMRouter
from cs_agent.pipeline.chunking import chunk_markdown

SPEC_DOC = """---
doc_id: DS-TRF-OIL-1000
doc_type: DS
product_code: TRF-OIL-1000
family: TRANSFORMER
---

# Oil-immersed Transformer 1000kVA — Datasheet

## 2. Technical specifications

### 2.1 Ratings

| Item | Value |
|---|---|
| Rated power | 1000 kVA (ONAN) |
| Vector group | Dyn11 |
"""


@pytest.fixture
def deps() -> GraphDeps:
    docs = KeywordRetriever(chunk_markdown(SPEC_DOC), "docs")
    return GraphDeps(
        llm=LLMRouter(Settings(llm_provider="fake")), docs=docs, cases=KeywordRetriever([], "cases")
    )
