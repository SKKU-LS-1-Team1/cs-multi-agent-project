"""기술문서 나누기·임베딩 → ChromaDB 적재 (CSA-18 · 담당 박종석).

- `docs` 컬렉션: data/raw/docs/**/*.md 를 절 단위로 (chunking.py)
- `cases` 컬렉션: data/processed/cases_seed.parquet (train에 연결된 사례만)

실행: `uv run --extra rag python -m cs_agent.pipeline.embed_docs`
"""

from cs_agent.config import get_settings
from cs_agent.pipeline.chunking import iter_doc_chunks


def main() -> None:
    import chromadb  # extra: rag

    s = get_settings()
    client = (
        chromadb.HttpClient(host=s.chroma_host, port=s.chroma_port)
        if s.chroma_host
        else chromadb.PersistentClient(path=str(s.raw_data_dir.parent / "chroma"))
    )
    # TODO(CSA-18): 임베딩 모델 결정 (다국어 15개 언어). 기본값은 Chroma 내장 모델.
    docs = client.get_or_create_collection("docs")
    chunks = iter_doc_chunks(s.raw_data_dir / "docs")
    docs.upsert(
        ids=[f"{c.doc_id}#{c.section or i}" for i, c in enumerate(chunks)],
        documents=[f"{c.title}\n{c.text}" for c in chunks],
        metadatas=[
            {
                "doc_id": c.doc_id,
                "section": c.section or "",
                "doc_type": c.metadata.get("doc_type", ""),
                "product_code": c.metadata.get("product_code", ""),
                "family": c.metadata.get("family", ""),
            }
            for c in chunks
        ],
    )
    print(f"docs: {len(chunks)} chunks")
    # TODO(CSA-18): cases 컬렉션 적재 (요약·제품·유형·에러코드·조치·최종 답변)


if __name__ == "__main__":
    main()
