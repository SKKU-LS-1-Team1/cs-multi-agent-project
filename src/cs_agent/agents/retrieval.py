"""④ 1차 검색 · ⑧ 근거 확정: 지식 검색 에이전트 (CSA-28 · 담당 박종석).

답변 작성과 챗봇이 함께 쓴다. ChromaDB 컬렉션 2개(기획서 7.1):
- `docs`: 공식 문서·FAQ·정책 (절 단위). 값·절차·정책의 근거. 값이 충돌하면 이쪽을 따른다.
- `cases`: 해결 사례. 비슷한 문의를 어떻게 풀었는지와 문장 본보기. 참고로만 쓴다.

정확히 맞아야 하는 값(사양·보증기간·에러코드)은 벡터 검색이 아니라 기준표 조회로 한다.
"""

import math
import re
from collections.abc import Iterable
from typing import Protocol

from cs_agent.config import get_settings
from cs_agent.pipeline.chunking import Chunk, iter_doc_chunks
from cs_agent.schemas import Evidence, Extraction

_TOKEN_RE = re.compile(r"[A-Za-z0-9가-힣.\-]+")


class Retriever(Protocol):
    def search(
        self, query: str, k: int = 5, where: dict[str, str] | None = None
    ) -> list[Evidence]: ...


class KeywordRetriever:
    """ChromaDB 없이 쓰는 TF-IDF 비슷한 키워드 검색. 테스트와 로컬 시연용."""

    def __init__(self, chunks: Iterable[Chunk], source: str = "docs") -> None:
        self.source = source
        self._chunks = list(chunks)
        self._tokens = [self._tokenize(f"{c.title} {c.text}") for c in self._chunks]
        df: dict[str, int] = {}
        for tokens in self._tokens:
            for t in tokens:
                df[t] = df.get(t, 0) + 1
        n = len(self._chunks) or 1
        self._idf = {t: math.log((n + 1) / (d + 0.5)) for t, d in df.items()}

    @staticmethod
    def _tokenize(text: str) -> set[str]:
        return {t.lower().strip(".") for t in _TOKEN_RE.findall(text) if len(t) > 1}

    def search(self, query: str, k: int = 5, where: dict[str, str] | None = None) -> list[Evidence]:
        q = self._tokenize(query)
        total = sum(self._idf.get(t, 0) for t in q) or 1
        scored = []
        for c, tokens in zip(self._chunks, self._tokens, strict=True):
            if where and any(c.metadata.get(key) != val for key, val in where.items()):
                continue
            score = sum(self._idf[t] for t in q & tokens) / total
            if score > 0:
                scored.append((score, c))
        scored.sort(key=lambda x: -x[0])
        return [
            Evidence(source=self.source, doc_id=c.doc_id, section=c.section, text=c.text, score=s)
            for s, c in scored[:k]
        ]


class ChromaRetriever:
    """TODO(CSA-18·CSA-28): 임베딩 모델 확정 후 pipeline/embed_docs.py와 같은 설정으로 맞춘다."""

    def __init__(self, collection: str) -> None:
        import chromadb  # extra: rag

        s = get_settings()
        self.source = collection
        client = chromadb.HttpClient(host=s.chroma_host, port=s.chroma_port)
        self._col = client.get_or_create_collection(collection)

    def search(self, query: str, k: int = 5, where: dict[str, str] | None = None) -> list[Evidence]:
        res = self._col.query(query_texts=[query], n_results=k, where=where or None)
        out = []
        for doc, meta, dist in zip(
            res["documents"][0], res["metadatas"][0], res["distances"][0], strict=True
        ):
            out.append(
                Evidence(
                    source=self.source,
                    doc_id=str(meta.get("doc_id")),
                    section=meta.get("section"),
                    text=doc,
                    score=1 - float(dist),
                )
            )
        return out


def default_retrievers() -> tuple[Retriever, Retriever]:
    s = get_settings()
    if s.chroma_host:
        return ChromaRetriever("docs"), ChromaRetriever("cases")
    docs_dir = s.raw_data_dir / "docs"
    chunks = iter_doc_chunks(docs_dir) if docs_dir.exists() else []
    return KeywordRetriever(chunks, "docs"), KeywordRetriever([], "cases")


def first_pass(docs: Retriever, cases: Retriever, text: str, k: int = 8) -> list[Evidence]:
    """유형이 정해지기 전 원문으로 넓게 가져온다 (N-01 병렬)."""
    return docs.search(text, k=k) + cases.search(text, k=3)


def finalize_evidence(
    candidates: list[Evidence], extraction: Extraction, k: int = 3
) -> list[Evidence]:
    """제품으로 거르고 다시 정렬한다. TODO(CSA-28): 유형별 문서 종류 가중치, 재정렬 모델."""
    code = extraction.product_code
    docs = [e for e in candidates if e.source == "docs" and (not code or code in e.doc_id)]
    cases = [e for e in candidates if e.source == "cases"]
    return sorted(docs, key=lambda e: -e.score)[:k] + cases[:2]
