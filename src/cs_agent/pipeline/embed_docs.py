# 임베딩 → PostgreSQL(pgvector) 적재 (CSA-18 · 담당 박종석 · Sprint 1)
# 실행 예: uv run --extra rag --extra llm --extra data python -m cs_agent.pipeline.embed_docs
#   (cases 입력 parquet 를 읽느라 data extra 도 필요)
# 문서만 점검: 위 명령 끝에 --target docs --dry-run
# 문서만 적재: 위 명령 끝에 --target docs (실제 호출은 LLM_PROVIDER=live 필요)
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
# - 테이블은 DB 에서 읽어(reflection) 쓴다. CSA-24의 정식 열 이름과 필수값에 맞춰 적재하며,
#   테이블·필수 열·vector 확장·벡터 차원이 맞지 않으면 API 호출 전에 멈춘다.
# - 엔진은 settings.database_url 로 직접 만든다. db/session.get_engine() 이 생기면 그걸 쓴다.
# - 긴 절을 나눈 조각은 id 가 "doc_id#section:2" (chunking.py). section 열은 같다.
# - text_hash에는 입력 글·모델·차원을 함께 반영한다. 모델 변경도 재임베딩 대상이다.
# - 임베딩 입력이 같아도 개정·인용 등 메타데이터 변경은 반영한다.
#   기존 사례의 검토 상태(edited/source_fix_needed/active)는 재적재로 초기화하지 않는다.
# - 개정으로 사라진 문서 조각 삭제는 --prune을 명시했을 때만 실행한다.
#   resolution_cases는 운영 사례가 함께 있으므로 삭제하지 않는다.
import argparse
import hashlib
import json
import logging
import math
import time
from collections.abc import Callable, Iterable, Sequence
from functools import lru_cache
from pathlib import Path
from typing import Any

import httpx

from cs_agent.config import REPO_ROOT, get_settings
from cs_agent.pipeline.chunking import Chunk, iter_doc_chunks

DOC_TABLE = "doc_chunks"
CASE_TABLE = "resolution_cases"
PROCESSED_DIR = REPO_ROOT / "data" / "processed"
MAX_RETRIES = 5
REQUEST_TIMEOUT_MS = 45_000
RETRY_STATUS = {408, 429, 500, 502, 503, 504, 529}
COMMIT_EVERY = 50  # 중간에 끊겨도 그때까지 넣은 벡터는 남도록
_LOGGER = logging.getLogger(__name__)

Row = dict[str, Any]
EmbedFn = Callable[[Sequence[str]], list[list[float]]]


@lru_cache
def _client() -> Any:
    from google import genai
    from google.genai import types

    settings = get_settings()
    if not settings.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY 가 없습니다 (.env 확인)")
    return genai.Client(
        api_key=settings.gemini_api_key,
        http_options=types.HttpOptions(
            timeout=REQUEST_TIMEOUT_MS,
            retry_options=types.HttpRetryOptions(attempts=1),
        ),
    )


def _validate_vector(values: Any, dimensions: int) -> list[float]:
    """pgvector에 넣기 전에 차원·유한한 숫자·코사인 검색 가능 여부를 확인한다."""
    if values is None or isinstance(values, (str, bytes)):
        raise ValueError("임베딩은 숫자 벡터여야 합니다")
    if len(values) != dimensions:
        raise ValueError(f"임베딩 차원이 설정({dimensions})과 다릅니다")
    try:
        vector = [float(value) for value in values]
    except (TypeError, ValueError) as exc:
        raise ValueError("임베딩에 숫자가 아닌 값이 있습니다") from exc
    if any(not math.isfinite(value) or abs(value) > 3.4028234663852886e38 for value in vector):
        raise ValueError("임베딩에 pgvector가 저장할 수 없는 숫자가 있습니다")
    if not any(vector):
        raise ValueError("영벡터는 코사인 검색에 사용할 수 없습니다")
    return vector


def embed(texts: Sequence[str]) -> list[list[float]]:
    """글마다 Gemini 임베딩 1개. 적재와 검색(agents/retrieval.py)이 같이 쓴다."""
    if not texts:
        return []
    settings = get_settings()
    if settings.llm_provider != "live":
        raise RuntimeError("실제 임베딩은 LLM_PROVIDER=live 설정이 필요합니다")
    if settings.embedding_dim <= 0 or any(not text.strip() for text in texts):
        raise ValueError("양수 임베딩 차원과 비어 있지 않은 입력이 필요합니다")
    from google.genai import errors, types

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
            except (errors.APIError, httpx.TimeoutException, httpx.NetworkError) as exc:
                status = getattr(exc, "code", None)
                if (
                    isinstance(exc, errors.APIError) and status not in RETRY_STATUS
                ) or attempt == MAX_RETRIES - 1:
                    raise
                # 키·고객 원문·예외 본문은 기록하지 않는다.
                _LOGGER.warning("Embedding retry: attempt=%d status=%s", attempt + 1, status)
                time.sleep(2**attempt * 5)
        if not response.embeddings or len(response.embeddings) != 1:
            raise ValueError("입력 글 하나에 임베딩 하나가 반환되어야 합니다")
        vectors.append(_validate_vector(response.embeddings[0].values, settings.embedding_dim))
    return vectors


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _embedding_hash(text: str, model: str, dimensions: int) -> str:
    return text_hash(json.dumps(["embedding-v1", model, dimensions, text], ensure_ascii=False))


def _text(value: Any) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    return str(value).strip()


def doc_rows(chunks: Iterable[Chunk]) -> list[Row]:
    """청크 → doc_chunks 행. text는 제품·문서 종류·제목 경로를 포함한 임베딩 입력.

    DB 열과 청크 ID·절 번호는 유지한다. 문맥이 바뀌면 text_hash도 바뀌어 재임베딩된다.
    """
    rows = []
    settings = get_settings()
    for chunk in chunks:
        heading = f"{chunk.section}. {chunk.title}"
        text = chunk.embedding_text
        rows.append(
            {
                "id": chunk.id,
                "doc_id": chunk.doc_id,
                "section": chunk.section,
                "title": heading,
                "doc_type": chunk.metadata.get("doc_type", ""),
                "product_code": chunk.metadata.get("product_code", ""),
                "family": chunk.metadata.get("family", ""),
                "revision": chunk.metadata.get("revision", ""),
                "language": chunk.metadata.get("language", ""),
                "text": text,
                "text_hash": _embedding_hash(
                    text, settings.embedding_model, settings.embedding_dim
                ),
            }
        )
    return rows


def case_text(row: Row) -> str:
    """임베딩할 글 = 문의 요약 + 원인 + 조치 + 최종 답변."""
    parts = [
        ("Summary", row["summary"]),
        ("Root cause", row["cause"]),
        ("Action", row["action"]),
        ("Final reply", row["final_reply"]),
    ]
    return "\n".join(f"{label}: {value}" for label, value in parts if value)


def case_rows(cases: Iterable[Row], final_replies: dict[str, str]) -> list[Row]:
    """cases_seed → resolution_cases 행. 최종 답변은 tickets.final_reply 를 ticket_id 로 붙인다."""
    rows = []
    settings = get_settings()
    for case in cases:
        ticket_id = _text(case.get("ticket_id"))
        if ticket_id not in final_replies or _text(case.get("data_split")) not in ("", "train"):
            raise ValueError("해결 사례는 학습 티켓에 연결된 train 사례만 적재할 수 있습니다")
        doc_id = _text(case.get("reference_doc_id"))
        section = _text(case.get("reference_section"))
        row = {
            "case_id": _text(case["case_id"]),
            "ticket_id": ticket_id,
            "category": _text(case.get("category_code")),
            "product_code": _text(case.get("product_code")),
            "product_family": _text(case.get("product_family")),
            "error_code": _text(case.get("error_code")),
            "summary": _text(case.get("case_summary")) or _text(case.get("symptom")),
            "cause": _text(case.get("root_cause")),
            "action": _text(case.get("action_taken")),
            "final_reply": _text(final_replies[ticket_id]),
            "cited": [f"{doc_id}#{section}" if section else doc_id] if doc_id else [],
            "resolved_by_dept": _text(case.get("resolved_by_dept")) or None,
            # 학습 데이터에는 상담원 리뷰 이력이 없으므로 승인·수정을 만들어 내지 않는다.
            "edited": False,
            "source_fix_needed": False,
            "data_split": "train",
            "active": True,
        }
        row["text"] = case_text(row)
        row["text_hash"] = _embedding_hash(
            row["text"], settings.embedding_model, settings.embedding_dim
        )
        rows.append(row)
    return rows


def _reflect(conn: Any, name: str, dimensions: int) -> Any:
    import sqlalchemy as sa

    if name not in (DOC_TABLE, CASE_TABLE) or conn.dialect.name not in ("postgresql", "sqlite"):
        raise ValueError("지원하지 않는 적재 테이블 또는 DB입니다")
    if not sa.inspect(conn).has_table(name):
        raise RuntimeError(f"{name} 테이블이 없습니다. CSA-24 마이그레이션(alembic upgrade)부터")
    if conn.dialect.name == "postgresql":
        enabled = conn.execute(
            sa.text("SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector')")
        ).scalar_one()
        if not enabled:
            raise RuntimeError("vector 확장이 없습니다. CSA-24 마이그레이션을 확인하세요")
        try:
            from pgvector.sqlalchemy import Vector
        except ImportError:
            raise RuntimeError(
                "pgvector 의존성이 없습니다. uv sync --extra rag 실행이 필요합니다"
            ) from None
    table = sa.Table(name, sa.MetaData(), autoload_with=conn)
    required = {"text_hash", "embedding", "id" if name == DOC_TABLE else "case_id"}
    if name == DOC_TABLE:
        required |= {"doc_id", "section", "title", "text"}
    else:
        required |= {
            "text",
            "summary",
            "cause",
            "action",
            "final_reply",
            "cited",
            "edited",
            "source_fix_needed",
            "active",
            "data_split",
        }
    if not required.issubset(table.c.keys()):
        raise RuntimeError(f"{name} 필수 열 누락: {sorted(required - set(table.c.keys()))}")
    if conn.dialect.name == "postgresql" and (
        not isinstance(table.c.embedding.type, Vector) or table.c.embedding.type.dim != dimensions
    ):
        raise RuntimeError(f"{name}.embedding은 vector({dimensions}) 형식이어야 합니다")
    return table


def sync_rows(
    conn: Any,
    table_name: str,
    key: str,
    rows: list[Row],
    embed_texts: Sequence[str],
    embed_fn: EmbedFn = embed,
    prune: bool = False,
    progress: Callable[[int, int], None] | None = None,
    *,
    dry_run: bool = False,
) -> dict[str, int]:
    """입력·모델·차원이 같고 벡터가 있으면 재호출 없이 기존 벡터를 유지한다.

    embed_texts[i] 가 rows[i] 의 임베딩할 글. prune=True 면 rows 에 없는 key 행을 지운다.
    dry_run은 DB 구조와 재임베딩 대상만 확인하고 API·DB 변경은 실행하지 않는다.
    skipped는 임베딩 생략 수이며, 메타데이터만 바뀐 행은 벡터를 보존하며 갱신한다.
    """
    import sqlalchemy as sa
    from sqlalchemy.dialects import postgresql, sqlite

    settings = get_settings()
    model = settings.embedding_model
    dimensions = settings.embedding_dim
    if dimensions <= 0 or not model.strip():
        raise ValueError("유효한 임베딩 모델·차원이 필요합니다")
    if len(rows) != len(embed_texts) or any(not text.strip() for text in embed_texts):
        raise ValueError("행 수와 임베딩 입력 수가 일치하고 모든 입력이 비어 있지 않아야 합니다")
    if prune and (not rows or table_name != DOC_TABLE):
        raise ValueError("삭제는 비어 있지 않은 전체 문서 목록으로만 실행할 수 있습니다")
    keys = [row[key] for row in rows]
    if any(not value for value in keys) or len(set(keys)) != len(keys):
        raise ValueError(f"{table_name}: {key} 가 비어 있거나 겹칩니다")
    table = _reflect(conn, table_name, dimensions)
    if key not in table.c:
        raise RuntimeError(f"{table_name}: {key} 열이 없습니다")

    current = {
        k: (h, has_vector)
        for k, h, has_vector in conn.execute(
            sa.select(table.c[key], table.c.text_hash, table.c.embedding.is_not(None))
        )
    }
    hashes = [_embedding_hash(text, model, dimensions) for text in embed_texts]
    todo = [i for i, value in enumerate(keys) if current.get(value) != (hashes[i], True)]
    if dry_run:
        return {
            "rows": len(rows),
            "embedded": 0,
            "skipped": len(rows) - len(todo),
            "removed": 0,
            "pending": len(todo),
        }

    insert = sqlite.insert if conn.dialect.name == "sqlite" else postgresql.insert  # sqlite: 테스트
    columns = set(table.c.keys())
    preserved = {"active", "edited", "source_fix_needed"} if table_name == CASE_TABLE else set()
    removed = 0
    try:
        for done, i in enumerate(todo, start=1):
            values = {k: v for k, v in rows[i].items() if k in columns}
            vectors = embed_fn([embed_texts[i]])
            if len(vectors) != 1:
                raise ValueError("행 하나에 벡터 하나가 필요합니다")
            values["embedding"] = _validate_vector(vectors[0], dimensions)
            values["text_hash"] = hashes[i]
            stmt = insert(table).values(**values)
            conn.execute(
                stmt.on_conflict_do_update(
                    index_elements=[key],
                    set_={k: stmt.excluded[k] for k in values if k != key and k not in preserved},
                )
            )
            if done % COMMIT_EVERY == 0:
                conn.commit()
            if progress:
                progress(done, len(todo))
        # 모델 호출이 필요 없는 행도 개정·검색 필터·인용 정보는 최신으로 유지한다.
        pending = set(todo)
        for i in range(len(rows)):
            if i in pending:
                continue
            values = {
                k: v
                for k, v in rows[i].items()
                if k in columns and k not in {key, "embedding", "text_hash"} | preserved
            }
            if values:
                conn.execute(
                    sa.update(table)
                    .where(
                        table.c[key] == keys[i],
                        sa.or_(*(table.c[k].is_distinct_from(v) for k, v in values.items())),
                    )
                    .values(**values)
                )
        if prune:
            stale = set(current) - set(keys)
            if stale:
                conn.execute(sa.delete(table).where(table.c[key].in_(stale)))
                removed = len(stale)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return {
        "rows": len(rows),
        "embedded": len(todo),
        "skipped": len(rows) - len(todo),
        "removed": removed,
        "pending": 0,
    }


def load_case_inputs(processed_dir: Path = PROCESSED_DIR) -> tuple[list[Row], dict[str, str]]:
    """cases_seed.parquet + train 티켓의 final_reply (CSA-17 결과, extra: data)."""
    import pandas as pd

    for filename in ("cases_seed.parquet", "tickets_train.parquet"):
        if not (processed_dir / filename).is_file():
            raise RuntimeError(f"{filename} 파일이 없습니다. CSA-17 데이터 정제를 먼저 실행하세요")
    cases = pd.read_parquet(processed_dir / "cases_seed.parquet")
    tickets = pd.read_parquet(processed_dir / "tickets_train.parquet")
    if not {"ticket_id", "final_reply", "data_split"}.issubset(tickets.columns):
        raise ValueError("학습 티켓에 ticket_id·final_reply·data_split 열이 필요합니다")
    if not tickets["data_split"].eq("train").all() or tickets["ticket_id"].duplicated().any():
        raise ValueError("학습 티켓의 split 또는 중복 ID를 확인하세요")
    replies = dict(zip(tickets["ticket_id"], tickets["final_reply"].map(_text), strict=True))
    return cases.to_dict("records"), replies


def main(argv: Sequence[str] | None = None) -> None:
    import sqlalchemy as sa

    parser = argparse.ArgumentParser(description="문서·학습 사례를 PostgreSQL(pgvector)에 적재")
    parser.add_argument("--target", choices=("docs", "cases", "all"), default="all")
    parser.add_argument("--dry-run", action="store_true", help="API·DB 변경 없이 적재 대상 점검")
    parser.add_argument("--prune", action="store_true", help="전체 문서 목록에서 사라진 조각 삭제")
    args = parser.parse_args(argv)

    def progress(done: int, total: int) -> None:
        print(f"  임베딩 {done}/{total}", end="\r", flush=True)

    settings = get_settings()
    jobs = []
    if args.target in ("docs", "all"):
        docs = doc_rows(iter_doc_chunks())
        if not docs:
            raise ValueError("적재할 문서 조각이 없습니다. 입력 경로를 확인하세요")
        jobs.append((DOC_TABLE, "id", docs, [r["text"] for r in docs]))
    if args.target in ("cases", "all"):
        cases = case_rows(*load_case_inputs())
        jobs.append((CASE_TABLE, "case_id", cases, [r["text"] for r in cases]))
    connect_args = (
        {"connect_timeout": 5}
        if sa.engine.make_url(settings.database_url).get_backend_name() == "postgresql"
        else {}
    )
    engine = sa.create_engine(settings.database_url, pool_pre_ping=True, connect_args=connect_args)
    try:
        with engine.connect() as conn:
            # all 실행은 두 테이블을 먼저 검사하여 두 번째 테이블 부재로 인한 낭비를 막는다.
            for table_name, _, _, _ in jobs:
                _reflect(conn, table_name, settings.embedding_dim)
            for table_name, key, rows, texts in jobs:
                result = sync_rows(
                    conn,
                    table_name,
                    key,
                    rows,
                    texts,
                    progress=progress,
                    prune=args.prune and table_name == DOC_TABLE,
                    dry_run=args.dry_run,
                )
                print(f"{table_name}: {result}")
    finally:
        engine.dispose()
    print(f"embedding model={settings.embedding_model} dim={settings.embedding_dim}")


if __name__ == "__main__":
    main()
