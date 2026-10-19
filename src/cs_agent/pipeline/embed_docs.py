# 임베딩 → ChromaDB 적재 (CSA-18 · 담당 박종석 · Sprint 1)
# 실행 예: uv run --extra rag --extra data python -m cs_agent.pipeline.embed_docs
#   (GEMINI_API_KEY 필요. 모델을 바꿨으면 --reset 으로 컬렉션을 지우고 다시 적재)
#
# 할 일
# 1. 임베딩 모델 결정: 15개 언어 문의로 영어 문서를 찾아야 하므로 다국어 모델. 결정 근거를 여기
#      적는다.
# 2. `docs` 컬렉션: pipeline/chunking.py 결과를 upsert.
#    id = "doc_id#section", document = 제목 + 본문,
#    metadata = doc_id, section, doc_type, product_code, family (검색 필터에 쓴다)
# 3. `cases` 컬렉션: data/processed/cases_seed.parquet (CSA-17 결과, train 연결 사례만)
#    document = 문의 요약 + 원인 + 조치 + 최종 답변, metadata = case_id, category, product_code,
#      error_code
# 4. 접속: settings.chroma_host 가 있으면 HttpClient, 없으면 data/chroma 에 PersistentClient.
# 5. 문서가 개정되면 다시 돌려도 되도록 upsert 로 (중복 없음).
#
# 임베딩 모델 결정 (할 일 1): Gemini 임베딩 API, gemini-embedding-001 · 768차원
# - 다국어: 100개 이상 언어를 한 벡터 공간에 넣어 15개 언어 문의 → 영어 문서 검색이 된다.
# - 이미 LLM 으로 Gemini 를 쓰고 있어 키·의존성(google-genai)이 늘지 않는다. 로컬 모델(torch,
#   fastembed)은 Docker 이미지가 커지고 첫 실행에 모델 파일을 받아야 한다.
# - 정식 버전(GA)을 쓴다. gemini-embedding-2 는 아직 preview 이고 task_type 이 무시된다는 보고가
#   있다. 문서는 RETRIEVAL_DOCUMENT, 검색어는 RETRIEVAL_QUERY 로 따로 임베딩해야 품질이 나온다.
#   chromadb 의 GoogleGeminiEmbeddingFunction 은 task_type 을 하나만 받아서 쓰지 않고, 벡터를
#   직접 만들어 넣는다. 검색(agents/retrieval.py)은 GeminiEmbedder.embed_query 를 쓴다.
# - 768차원: 3072 보다 저장·검색이 가볍고 품질 차이는 작다. 3072 가 아니면 API 가 정규화해 주지
#   않으므로 직접 L2 정규화한다. 거리 함수는 cosine.
# - 모델·차원은 settings(GEMINI_MODEL_EMBED·GEMINI_EMBED_DIM)에 있고 컬렉션 metadata 에도 남긴다.
#   다른 모델로 만든 컬렉션에 섞어 넣지 않도록 적재 전에 확인한다.
import argparse
import math
import time
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path
from typing import Any, Protocol

from cs_agent.config import REPO_ROOT, get_settings
from cs_agent.pipeline.chunking import Chunk, iter_doc_chunks

DOCS_COLLECTION = "docs"
CASES_COLLECTION = "cases"
LOCAL_CHROMA_DIR = REPO_ROOT / "data" / "chroma"
PROCESSED_DIR = REPO_ROOT / "data" / "processed"
EMBED_BATCH_SIZE = 100  # Gemini embed_content 한 번에 보낼 수 있는 최대 개수
MAX_RETRIES = 4


class Embedder(Protocol):
    model: str
    dim: int

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


def _normalize(vector: Sequence[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vector)) or 1.0
    return [v / norm for v in vector]


class GeminiEmbedder:
    """Gemini 임베딩. 문서와 검색어의 task_type 을 나눠 쓴다 (extra: rag)."""

    def __init__(self, model: str | None = None, dim: int | None = None, api_key: str = ""):
        from google import genai

        settings = get_settings()
        self.model = model or settings.gemini_model_embed
        self.dim = dim or settings.gemini_embed_dim
        api_key = api_key or settings.gemini_api_key
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY 가 없습니다 (.env 확인)")
        self._client = genai.Client(api_key=api_key)

    def _embed(self, texts: Sequence[str], task_type: str) -> list[list[float]]:
        from google.genai import errors, types

        config = types.EmbedContentConfig(task_type=task_type, output_dimensionality=self.dim)
        vectors: list[list[float]] = []
        for start in range(0, len(texts), EMBED_BATCH_SIZE):
            batch = list(texts[start : start + EMBED_BATCH_SIZE])
            for attempt in range(MAX_RETRIES):
                try:
                    response = self._client.models.embed_content(
                        model=self.model, contents=batch, config=config
                    )
                    break
                except errors.APIError as e:  # 429 한도·5xx 는 잠시 뒤 다시
                    if e.code not in (429, 500, 503) or attempt == MAX_RETRIES - 1:
                        raise
                    time.sleep(2**attempt * 5)
            vectors += [_normalize(e.values) for e in response.embeddings]
        return vectors

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return self._embed(texts, "RETRIEVAL_DOCUMENT")

    def embed_query(self, text: str) -> list[float]:
        return self._embed([text], "RETRIEVAL_QUERY")[0]


def get_client() -> Any:
    """settings.chroma_host 가 있으면 HttpClient, 없으면 data/chroma 에 PersistentClient."""
    import chromadb

    settings = get_settings()
    if settings.chroma_host:
        return chromadb.HttpClient(host=settings.chroma_host, port=settings.chroma_port)
    LOCAL_CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(LOCAL_CHROMA_DIR))


def get_collection(client: Any, name: str, embedder: Embedder) -> Any:
    """임베딩 모델을 metadata 에 남긴 컬렉션. 다른 모델로 만든 컬렉션이면 멈춘다."""
    collection = client.get_or_create_collection(
        name,
        embedding_function=None,
        metadata={"embed_model": embedder.model, "embed_dim": embedder.dim},
        configuration={"hnsw": {"space": "cosine"}},
    )
    metadata = collection.metadata or {}
    if (metadata.get("embed_model"), metadata.get("embed_dim")) != (embedder.model, embedder.dim):
        raise RuntimeError(
            f"'{name}' 컬렉션은 {metadata.get('embed_model')}·{metadata.get('embed_dim')} 로 "
            f"만들어졌습니다. --reset 으로 지우고 다시 적재하세요."
        )
    return collection


def doc_records(chunks: Iterable[Chunk]) -> tuple[list[str], list[str], list[dict[str, Any]]]:
    """청크 → (ids, documents, metadatas). document = 문서 제목 · 절 제목 + 본문."""
    ids, documents, metadatas = [], [], []
    for chunk in chunks:
        doc_title = chunk.metadata.get("title", "")
        heading = f"{chunk.section}. {chunk.title}"
        ids.append(chunk.id)
        documents.append(f"{doc_title} — {heading}\n\n{chunk.text}" if doc_title else chunk.text)
        metadatas.append(
            {
                "doc_id": chunk.doc_id,
                "section": chunk.section,
                "part": chunk.part,
                "doc_type": chunk.metadata.get("doc_type", ""),
                "product_code": chunk.metadata.get("product_code", ""),
                "family": chunk.metadata.get("family", ""),
                "title": heading,
            }
        )
    return ids, documents, metadatas


def _text(value: Any) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    return str(value).strip()


def case_records(
    cases: Iterable[dict[str, Any]], final_replies: dict[str, str]
) -> tuple[list[str], list[str], list[dict[str, Any]]]:
    """사례 → (ids, documents, metadatas). document = 문의 요약 + 원인 + 조치 + 최종 답변.

    최종 답변은 tickets.final_reply 에 있어서 ticket_id 로 붙인다.
    """
    ids, documents, metadatas = [], [], []
    for case in cases:
        parts = [
            ("Summary", _text(case.get("case_summary")) or _text(case.get("symptom"))),
            ("Root cause", _text(case.get("root_cause"))),
            ("Action", _text(case.get("action_taken"))),
            ("Final reply", final_replies.get(_text(case.get("ticket_id")), "")),
        ]
        ids.append(_text(case["case_id"]))
        documents.append("\n".join(f"{label}: {value}" for label, value in parts if value))
        metadatas.append(
            {
                "case_id": _text(case["case_id"]),
                "ticket_id": _text(case.get("ticket_id")),
                "category": _text(case.get("category_code")),
                "product_code": _text(case.get("product_code")),
                "family": _text(case.get("product_family")),
                "error_code": _text(case.get("error_code")),
            }
        )
    return ids, documents, metadatas


def upsert(
    collection: Any,
    records: tuple[list[str], list[str], list[dict[str, Any]]],
    embedder: Embedder,
    progress: Callable[[int, int], None] | None = None,
) -> tuple[int, int]:
    """upsert 하고, 이번 입력에 없는 id(개정으로 사라진 절)는 지운다. → (적재, 삭제) 건수."""
    ids, documents, metadatas = records
    if len(set(ids)) != len(ids):
        raise ValueError(f"{collection.name}: id 가 겹칩니다")
    for start in range(0, len(ids), EMBED_BATCH_SIZE):
        end = start + EMBED_BATCH_SIZE
        collection.upsert(
            ids=ids[start:end],
            documents=documents[start:end],
            metadatas=metadatas[start:end],
            embeddings=embedder.embed_documents(documents[start:end]),
        )
        if progress:
            progress(min(end, len(ids)), len(ids))

    stale = sorted(set(collection.get(include=[])["ids"]) - set(ids))
    if stale:
        collection.delete(ids=stale)
    return len(ids), len(stale)


def load_case_inputs(processed_dir: Path = PROCESSED_DIR) -> tuple[list[dict], dict[str, str]]:
    """cases_seed.parquet + train 티켓의 final_reply (CSA-17 결과, extra: data)."""
    import pandas as pd

    cases = pd.read_parquet(processed_dir / "cases_seed.parquet")
    tickets = pd.read_parquet(processed_dir / "tickets_train.parquet")
    replies = dict(zip(tickets["ticket_id"], tickets["final_reply"].map(_text), strict=True))
    return cases.to_dict("records"), replies


def main() -> None:
    parser = argparse.ArgumentParser(description="기술문서·해결 사례를 ChromaDB 에 적재한다")
    parser.add_argument("--reset", action="store_true", help="컬렉션을 지우고 새로 만든다")
    args = parser.parse_args()

    embedder = GeminiEmbedder()
    client = get_client()
    if args.reset:
        for name in (DOCS_COLLECTION, CASES_COLLECTION):
            if name in [c.name for c in client.list_collections()]:
                client.delete_collection(name)

    def progress(done: int, total: int) -> None:
        print(f"  {done}/{total}", end="\r", flush=True)

    jobs = [
        (DOCS_COLLECTION, lambda: doc_records(iter_doc_chunks())),
        (CASES_COLLECTION, lambda: case_records(*load_case_inputs())),
    ]
    for name, build in jobs:
        collection = get_collection(client, name, embedder)
        loaded, removed = upsert(collection, build(), embedder, progress)
        print(f"{name}: upsert={loaded}, removed_stale={removed}, total={collection.count()}")
    print(f"embed model={embedder.model} dim={embedder.dim}")


if __name__ == "__main__":
    main()
