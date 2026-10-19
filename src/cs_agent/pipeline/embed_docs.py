# 임베딩 → PostgreSQL(pgvector) 적재 (CSA-18 · 담당 박종석 · Sprint 1)
# 실행 예: uv run --extra rag --extra llm --extra data python -m cs_agent.pipeline.embed_docs
#   (cases 입력 parquet 를 읽느라 data extra 도 필요)
#
# 결정 (팀장 확정)
# - 벡터 저장소: ChromaDB 대신 PostgreSQL + pgvector. 테이블은 db/models.py (CSA-24) 의
#   doc_chunks, resolution_cases.embedding.
# - 임베딩 모델: settings.embedding_model = gemini-embedding-2, settings.embedding_dim = 1536.
#   15개 언어 문의로 영어 문서를 찾는 다국어 모델. 한·영 같은 뜻 유사도 0.75, 다른 뜻 0.44 확인.
#   비교한 gemini-embedding-001 (PR #10) 은 task_type·묶음 호출이 되지만, 팀은 2 로 간다.
#   기본 3072차원은 pgvector HNSW 인덱스 한도(2000)를 넘어서 output_dimensionality=1536 으로 받는다.
#
# 할 일
# 1. embed(texts) → list[list[float]]: google-genai (extra: llm) 로 부른다.
#      client.models.embed_content(model=settings.embedding_model, contents=text,
#          config=EmbedContentConfig(output_dimensionality=settings.embedding_dim))
#    ⚠️ gemini-embedding-2 는 contents 에 글 여러 개를 목록으로 넣으면 하나로 합쳐 벡터 1개만
#    돌려준다. 글 하나당 한 번씩 부른다 (약 0.5초/건 → 1,500건 ≈ 12분, 분당 호출 제한 주의).
#    task_type(RETRIEVAL_QUERY/DOCUMENT)은 gemini-embedding-2 가 무시한다 (같은 글이면 같은 벡터,
#    2026-10-19 확인). 적재·검색 모두 같은 embed() 를 쓰면 된다.
# 2. docs: pipeline/chunking.py 결과(약 900조각)를 doc_chunks 에 upsert.
#    id = "doc_id#section", text = 제목 + 본문,
#    doc_id·section·doc_type·product_code·family 열(검색 필터용).
# 3. cases: data/processed/cases_seed.parquet (CSA-17 결과, train 연결 568건)을 resolution_cases 에
#    upsert. 임베딩할 글 = 문의 요약 + 원인 + 조치 + 최종 답변. data_split = "train".
# 4. 문서가 개정되면 다시 돌려도 되도록 upsert 로 (중복 없음). 글이 안 바뀐 행은 임베딩을 다시
#    부르지 않는다 (text 해시 비교) — 비용·시간 절약.
#
# 구현 메모
# - 테이블은 ORM 클래스 대신 DB 에서 읽어(reflection) 쓴다. db/models.py 클래스 이름이 정해지기
#   전에도 테이블·열 이름(위 주석과 models.py 주석)만 맞으면 동작한다. 테이블에 없는 열은 넣지
#   않는다. 테이블이 없으면 CSA-24 마이그레이션부터 돌리라고 알리고 멈춘다.
# - 엔진은 settings.database_url 로 직접 만든다. db/session.get_engine() 이 생기면 그걸 쓴다.
# - 긴 절을 나눈 조각은 id 가 "doc_id#section:2" (chunking.py). section 열은 같다.
# - doc_chunks 에서 이번 문서에 없는 id(개정으로 사라진 절)는 지운다. resolution_cases 는 상담원
#   피드백으로 들어온 live 사례가 같이 있어서 지우지 않는다.
import hashlib
import math
import time
from collections.abc import Callable, Iterable, Sequence
from functools import lru_cache
from pathlib import Path
from typing import Any

from cs_agent.config import REPO_ROOT, get_settings
from cs_agent.pipeline.chunking import Chunk, iter_doc_chunks

DOC_TABLE = "doc_chunks"
CASE_TABLE = "resolution_cases"
PROCESSED_DIR = REPO_ROOT / "data" / "processed"
MAX_RETRIES = 5
COMMIT_EVERY = 50  # 중간에 끊겨도 그때까지 넣은 벡터는 남도록

Row = dict[str, Any]
EmbedFn = Callable[[Sequence[str]], list[list[float]]]


@lru_cache
def _client() -> Any:
    from google import genai

    settings = get_settings()
    if not settings.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY 가 없습니다 (.env 확인)")
    return genai.Client(api_key=settings.gemini_api_key)


def embed(texts: Sequence[str]) -> list[list[float]]:
    """글마다 Gemini 임베딩 1개. 적재와 검색(agents/retrieval.py)이 같이 쓴다."""
    from google.genai import errors, types

    settings = get_settings()
    client = _client()
    config = types.EmbedContentConfig(output_dimensionality=settings.embedding_dim)

    vectors = []
    for text in texts:  # 목록으로 보내면 벡터 1개로 합쳐지므로 하나씩
        for attempt in range(MAX_RETRIES):
            try:
                response = client.models.embed_content(
                    model=settings.embedding_model, contents=text, config=config
                )
                break
            except errors.APIError as e:  # 429 분당 한도·5xx 는 잠시 뒤 다시
                if e.code not in (429, 500, 503) or attempt == MAX_RETRIES - 1:
                    raise
                time.sleep(2**attempt * 5)
        vectors.append(list(response.embeddings[0].values))
    return vectors


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _text(value: Any) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    return str(value).strip()


def doc_rows(chunks: Iterable[Chunk]) -> list[Row]:
    """청크 → doc_chunks 행. text = 문서 제목 · 절 제목 + 본문 (이 글을 임베딩한다)."""
    rows = []
    for chunk in chunks:
        doc_title = chunk.metadata.get("title", "")
        heading = f"{chunk.section}. {chunk.title}"
        text = f"{doc_title} — {heading}\n\n{chunk.text}" if doc_title else chunk.text
        rows.append(
            {
                "id": chunk.id,
                "doc_id": chunk.doc_id,
                "section": chunk.section,
                "title": heading,
                "doc_type": chunk.metadata.get("doc_type", ""),
                "product_code": chunk.metadata.get("product_code", ""),
                "family": chunk.metadata.get("family", ""),
                "text": text,
                "text_hash": text_hash(text),
            }
        )
    return rows


def case_text(row: Row) -> str:
    """임베딩할 글 = 문의 요약 + 원인 + 조치 + 최종 답변."""
    parts = [
        ("Summary", row["summary"]),
        ("Root cause", row["cause"]),
        ("Action", row["action_taken"]),
        ("Final reply", row["final_reply"]),
    ]
    return "\n".join(f"{label}: {value}" for label, value in parts if value)


def case_rows(cases: Iterable[Row], final_replies: dict[str, str]) -> list[Row]:
    """cases_seed → resolution_cases 행. 최종 답변은 tickets.final_reply 를 ticket_id 로 붙인다."""
    rows = []
    for case in cases:
        ticket_id = _text(case.get("ticket_id"))
        row = {
            "case_id": _text(case["case_id"]),
            "ticket_id": ticket_id,
            "category": _text(case.get("category_code")),
            "product_code": _text(case.get("product_code")),
            "error_code": _text(case.get("error_code")),
            "summary": _text(case.get("case_summary")) or _text(case.get("symptom")),
            "cause": _text(case.get("root_cause")),
            "action_taken": _text(case.get("action_taken")),
            "final_reply": final_replies.get(ticket_id, ""),
            "reference_doc_id": _text(case.get("reference_doc_id")),
            "data_split": "train",
            "searchable": True,
        }
        row["text_hash"] = text_hash(case_text(row))
        rows.append(row)
    return rows


def _reflect(conn: Any, name: str) -> Any:
    import sqlalchemy as sa

    if not sa.inspect(conn).has_table(name):
        raise RuntimeError(f"{name} 테이블이 없습니다. CSA-24 마이그레이션(alembic upgrade)부터")
    try:  # vector 열을 Vector 타입으로 읽게 등록한다 (extra: rag)
        import pgvector.sqlalchemy  # noqa: F401
    except ImportError:
        pass
    return sa.Table(name, sa.MetaData(), autoload_with=conn)


def sync_rows(
    conn: Any,
    table_name: str,
    key: str,
    rows: list[Row],
    embed_texts: Sequence[str],
    embed_fn: EmbedFn = embed,
    prune: bool = False,
    progress: Callable[[int, int], None] | None = None,
) -> dict[str, int]:
    """rows 를 upsert 한다. text_hash 가 같고 벡터가 있는 행은 임베딩을 다시 부르지 않는다.

    embed_texts[i] 가 rows[i] 의 임베딩할 글. prune=True 면 rows 에 없는 key 행을 지운다.
    """
    import sqlalchemy as sa
    from sqlalchemy.dialects import postgresql, sqlite

    table = _reflect(conn, table_name)
    keys = [row[key] for row in rows]
    if len(set(keys)) != len(keys):
        raise ValueError(f"{table_name}: {key} 가 겹칩니다")

    current = {
        k: (h, has_vector)
        for k, h, has_vector in conn.execute(
            sa.select(table.c[key], table.c.text_hash, table.c.embedding.is_not(None))
        )
    }
    todo = [i for i, row in enumerate(rows) if current.get(row[key]) != (row["text_hash"], True)]

    insert = sqlite.insert if conn.dialect.name == "sqlite" else postgresql.insert  # sqlite: 테스트
    columns = set(table.c.keys())
    for done, i in enumerate(todo, start=1):
        values = {k: v for k, v in rows[i].items() if k in columns}
        values["embedding"] = embed_fn([embed_texts[i]])[0]
        stmt = insert(table).values(**values)
        conn.execute(
            stmt.on_conflict_do_update(
                index_elements=[key], set_={k: stmt.excluded[k] for k in values if k != key}
            )
        )
        if done % COMMIT_EVERY == 0:
            conn.commit()
        if progress:
            progress(done, len(todo))

    removed = 0
    if prune:
        stale = set(current) - set(keys)
        if stale:
            conn.execute(sa.delete(table).where(table.c[key].in_(stale)))
            removed = len(stale)
    conn.commit()
    return {
        "rows": len(rows),
        "embedded": len(todo),
        "skipped": len(rows) - len(todo),
        "removed": removed,
    }


def load_case_inputs(processed_dir: Path = PROCESSED_DIR) -> tuple[list[Row], dict[str, str]]:
    """cases_seed.parquet + train 티켓의 final_reply (CSA-17 결과, extra: data)."""
    import pandas as pd

    cases = pd.read_parquet(processed_dir / "cases_seed.parquet")
    tickets = pd.read_parquet(processed_dir / "tickets_train.parquet")
    replies = dict(zip(tickets["ticket_id"], tickets["final_reply"].map(_text), strict=True))
    return cases.to_dict("records"), replies


def main() -> None:
    import sqlalchemy as sa

    def progress(done: int, total: int) -> None:
        print(f"  임베딩 {done}/{total}", end="\r", flush=True)

    engine = sa.create_engine(get_settings().database_url)
    docs = doc_rows(iter_doc_chunks())
    cases = case_rows(*load_case_inputs())
    with engine.connect() as conn:
        result = sync_rows(
            conn, DOC_TABLE, "id", docs, [r["text"] for r in docs], prune=True, progress=progress
        )
        print(f"{DOC_TABLE}: {result}")
    with engine.connect() as conn:
        result = sync_rows(
            conn, CASE_TABLE, "case_id", cases, [case_text(r) for r in cases], progress=progress
        )
        print(f"{CASE_TABLE}: {result}")
    settings = get_settings()
    print(f"embedding model={settings.embedding_model} dim={settings.embedding_dim}")


if __name__ == "__main__":
    main()
