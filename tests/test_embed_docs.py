import hashlib
import math

import pytest

from cs_agent.pipeline.chunking import Chunk
from cs_agent.pipeline.embed_docs import (
    case_records,
    doc_records,
    get_collection,
    upsert,
)

chromadb = pytest.importorskip("chromadb")


class FakeEmbedder:
    """API 없이 쓰는 결정적 임베더. 같은 글이면 같은 벡터."""

    model = "fake-embed"
    dim = 8

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_query(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode()).digest()
        vector = [b - 128 for b in digest[: self.dim]]
        norm = math.sqrt(sum(v * v for v in vector)) or 1.0
        return [v / norm for v in vector]


def _chunk(section: str, text: str, part: int = 1) -> Chunk:
    metadata = {
        "doc_id": "DS-TEST-1",
        "title": "Test product — Datasheet",
        "doc_type": "DS",
        "product_code": "TEST-1",
        "family": "LV_BREAKER",
    }
    return Chunk("DS-TEST-1", section, "Ratings", text, metadata, part)


def test_doc_records_build_ids_documents_and_filters() -> None:
    ids, documents, metadatas = doc_records([_chunk("2.1", "| A | B |"), _chunk("2.1", "x", 2)])

    assert ids == ["DS-TEST-1#2.1", "DS-TEST-1#2.1:2"]
    assert documents[0] == "Test product — Datasheet — 2.1. Ratings\n\n| A | B |"
    assert metadatas[0] == {
        "doc_id": "DS-TEST-1",
        "section": "2.1",
        "part": 1,
        "doc_type": "DS",
        "product_code": "TEST-1",
        "family": "LV_BREAKER",
        "title": "2.1. Ratings",
    }


def test_case_records_join_final_reply_and_drop_missing_values() -> None:
    case = {
        "case_id": "RC-0001",
        "ticket_id": "CSV1-000002",
        "category_code": "INSTALL",
        "product_code": "VCB-25kV-1250",
        "product_family": "MV_EQUIP",
        "error_code": float("nan"),
        "case_summary": "VCB contact wear indicator at limit.",
        "root_cause": "Vacuum interrupter end of life",
        "action_taken": "Replace vacuum interrupter",
    }

    ids, documents, metadatas = case_records([case], {"CSV1-000002": "An engineer is assigned."})

    assert ids == ["RC-0001"]
    assert documents[0] == (
        "Summary: VCB contact wear indicator at limit.\n"
        "Root cause: Vacuum interrupter end of life\n"
        "Action: Replace vacuum interrupter\n"
        "Final reply: An engineer is assigned."
    )
    assert metadatas[0]["error_code"] == ""
    assert metadatas[0]["category"] == "INSTALL"


def test_upsert_is_idempotent_and_removes_stale_ids(tmp_path) -> None:
    client = chromadb.PersistentClient(path=str(tmp_path))
    embedder = FakeEmbedder()
    collection = get_collection(client, "docs", embedder)
    first = doc_records([_chunk("1", "Overview"), _chunk("2.1", "Ratings table")])

    assert upsert(collection, first, embedder) == (2, 0)
    assert upsert(collection, first, embedder) == (2, 0)
    assert collection.count() == 2

    revised = doc_records([_chunk("2.1", "Ratings table rev B")])
    assert upsert(collection, revised, embedder) == (1, 1)
    assert collection.get()["ids"] == ["DS-TEST-1#2.1"]

    hit = collection.query(
        query_embeddings=[embedder.embed_query(revised[1][0])],
        n_results=1,
        where={"product_code": "TEST-1"},
    )
    assert hit["ids"] == [["DS-TEST-1#2.1"]]


def test_get_collection_rejects_other_embedding_model(tmp_path) -> None:
    client = chromadb.PersistentClient(path=str(tmp_path))
    get_collection(client, "docs", FakeEmbedder())

    other = FakeEmbedder()
    other.model = "another-model"
    with pytest.raises(RuntimeError, match="--reset"):
        get_collection(client, "docs", other)
