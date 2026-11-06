# 지식 검색 에이전트 — ④ 1차 검색 · ⑧ 근거 확정 (CSA-28 · 담당 박종석 · Sprint 1)
#
# 답변 작성(⑨)과 챗봇(CSA-32)이 함께 쓴다. 벡터 검색은 PostgreSQL + pgvector (기획서 7.1, 팀장 확정:
# ChromaDB 대신). 검색 대상 2개:
# - `docs` = doc_chunks 테이블: 공식 문서·FAQ·정책을 절 단위로 (CSA-18에서 적재). 값·절차·정책의
#     근거. 값이 충돌하면 이쪽.
# - `cases` = 해결 사례 패턴 DB (case_patterns + resolution_cases.pattern_id,
#     agents/case_patterns.py):
#     처리된 문의를 같은 고장(원인·조치) 패턴으로 묶어 배우고, 새 문의를 패턴 설명과 비교해 찾는다.
#     지난 문의 글을 임베딩해서 찾지 않는다 (CSA-28 피드백 — 근거는 case_patterns.py 머리말).
#     비슷한 문의를 어떻게 풀었는지, 문장 본보기. 참고로만.
#
# 할 일
# 1. Retriever 규약: search(query, k, where) → list[Evidence]. where 는 메타데이터 필터
#    (product_code, doc_type, family). Evidence.source 에 "docs" / "cases" 를 넣는다.
# 2. PgVectorRetriever(table): 질문을 적재와 같은 pipeline/embed_docs.embed 로 임베딩해서
#    `ORDER BY embedding <=> :query LIMIT k` (코사인 거리, extra: rag).
#    where 는 같은 SQL 의 WHERE 로 (product_code = … AND …). score = 1 - 거리.
#    임베딩 모델·차원은 적재와 반드시 같은 settings.embedding_model / embedding_dim 을 쓴다.
# 3. default_retrievers(): DB 에 연결되고 doc_chunks 가 비어 있지 않으면 pgvector 2개, 아니면 로컬
#    개발용 대체 구현(data/raw/docs 를 pipeline/chunking.py 로 읽어 키워드 검색)을 돌려준다.
# 4. first_pass(): 유형이 정해지기 전에 원문으로 넓게 가져온다 (분류·추출과 병렬, N-01).
#    docs top-8 + 패턴 top-8 (패턴은 근거 확정에서 제품군·적용 제품·에러코드로 거른 뒤 2개).
# 5. finalize_evidence(): 추출된 제품으로 거르고, 유형별로 문서 종류 가중치(사양→DS, 설치→IG,
#    불량→TG, 펌웨어→RN …)를 줘서 재정렬한다. docs 3개 + cases 2개 정도.
# 6. 사양값·보증기간·에러코드처럼 정확히 맞아야 하는 값은 벡터 검색이 아니라 기준표 조회로 한다
#    (CSA-19). 에러코드가 있으면 고장 카탈로그 정확 조회, 없으면 증상으로 사례 검색.
#
# 완료 기준
# - valid: 근거 일치율 K3 (reference_doc_id + reference_section 이 top-3 안) 측정·보고
# - test 티켓에 연결된 사례가 resolution_cases 검색 대상에 없음
#
# 참고: 기획서 v10 7.1, 에이전트_구조_제안.md 6장
#
# 정해 둔 것
# - Evidence.metadata 에 doc_type·product_code·family·title(사례는 category·error_code 등)을 싣는다.
#   finalize_evidence 가 검색기 없이 후보만으로 거르고 재정렬하려면 필요하다.
# - finalize_evidence 는 유형(category)을 키워드 인자로 받는다 (graph/builder.py evidence 노드).
# - 유형별 우선 문서는 tickets 정답 분포로 정했다 (valid: TECH_SPEC·COMPLIANCE→DS, DEFECT→TG,
#   FW_UPDATE→RN, INSTALL→IG·TG, ORDER_LEAD·QUOTE→POL-ORDER, RETURN→POL-RETURN,
#   WARRANTY→POL-WARRANTY, MANUAL 은 여러 종류라 가중치 없음).
# - 에러코드(할 일 6): 원문에 고장 카탈로그(fault_catalog.csv)의 코드가 있으면 first_pass 가 TG 절을
#   따로 더 찾고, finalize 는 절 제목이 그 코드인 TG 절을 맨 위로 올린다 (TG 절 제목이
#   "3.1 E.OC — ..." 형식이라 정확히 맞출 수 있다). 진단형 유형(불량·설치·펌웨어)이거나 유형을
#   모를 때만 올린다 — tickets 의 에러코드 문의 234건은 모두 DEFECT·TG 정답이다.
# - 키워드 대체 구현의 cases 는 data/raw 의 사례 중 train 티켓에 연결된 것만 패턴으로 묶는다
#   (완료 기준 2, case_patterns.train_cases).
# - K3 측정: uv run python -m cs_agent.agents.retrieval --split valid
# - 지식 그래프 (CSA-71): GRAPH_ENABLED=true 면 finalize_evidence 의 사례 자리를
#   agents/knowledge_graph.py 검색 결과로 바꾼다 (제품·에러코드 경로로 좁힌 고장 위 2개).
#   꺼져 있거나 Neo4j·임베딩이 실패하면 아래 패턴 DB 경로 그대로.
# - reranker (CSA-81 · 김동규): 벡터 점수 + 규칙 가산점으로 정렬한 docs 후보 위 RERANK_POOL 개를
#   "이 절이 문의에 답하는 내용인가" 로 판단 모델(llm.judge, task "rerank")에 절마다 병렬로 묻고,
#   관련도(yes 확신도, no 면 1 - 확신도) × settings.rerank_weight 를 점수에 더해 다시 정렬한다.
#   벡터 유사도는 "비슷한 말" 이라 같은 제품의 다른 절이 앞에 오는 일이 많아서다 (멘토링 2번).
#   에러코드가 절 제목과 정확히 맞는 TG 절(ERROR_CODE_BONUS)은 정확 조회라 판단과 상관없이
#   위에 둔다.
#   RERANK_ENABLED=false · 라우터 없음 · LLM 꺼짐(fake) · 호출 실패면 지금 규칙 정렬 그대로.
#   비교: uv run python -m cs_agent.agents.retrieval --split valid --rerank (끔/켬 K3 를 같이 출력)
import argparse
import contextvars
import csv
import logging
import math
import re
import time
from collections import Counter
from collections.abc import Callable, Iterable, Sequence
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from pathlib import Path
from typing import Any, Protocol

from cs_agent.config import get_settings
from cs_agent.domain import BUNDLE_OF, Bundle, Category
from cs_agent.schemas import Evidence, Extraction

_LOGGER = logging.getLogger(__name__)

DOCS_K = 8
CASES_K = 8  # 패턴 후보 (근거 확정에서 거르므로 넉넉히)
FINAL_CASES_K = 2
ERROR_CODE_K = 3
TYPE_BONUS = 0.3  # 유형에 맞는 문서 종류
ERROR_CODE_BONUS = 1.0  # 절 제목이 문의의 에러코드와 같은 TG 절 (정확 조회라 가장 우선)
RERANK_TASK = "rerank"
RERANK_POOL = 8  # 규칙 정렬 위 몇 개를 판단 모델에 다시 묻는가 (first_pass docs top-8 과 같게)
RERANK_WORKERS = 8
RERANK_TEXT_CHARS = 1500  # 절 본문은 앞부분만 (긴 절 = 같은 절 조각 중 점수 높은 것)

# 유형별로 먼저 볼 문서. "DS" 는 doc_type, "POL-ORDER" 처럼 '-' 가 있으면 doc_id
PREFERRED_DOCS: dict[Category, tuple[str, ...]] = {
    Category.TECH_SPEC: ("DS",),
    Category.COMPLIANCE: ("DS",),
    Category.DEFECT: ("TG",),
    Category.FW_UPDATE: ("RN",),
    Category.INSTALL: ("IG", "TG"),
    Category.ORDER_LEAD: ("POL-ORDER",),
    Category.QUOTE: ("POL-ORDER",),
    Category.RETURN: ("POL-RETURN",),
    Category.WARRANTY: ("POL-WARRANTY",),
}

# 검색 필터로 쓸 수 있는 열 (SQL 에 그대로 들어가므로 이 목록만 받는다)
DOC_FILTERS = ("doc_type", "product_code", "family", "doc_id")
CASE_FILTERS = ("category", "product_code", "error_code")


class Retriever(Protocol):
    def search(
        self, query: str, k: int = 5, where: dict[str, str] | None = None
    ) -> list[Evidence]: ...


# 키워드 검색 (로컬 개발용 대체 구현) -----------------------------------------------------------

_TOKEN = re.compile(r"[a-z0-9]+(?:\.[a-z0-9]+)*")


def _tokens(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


class KeywordRetriever:
    """질문 단어가 글에 얼마나 들어 있는지(idf 가중)로 고른다. 영어 외 문의에는 약하다."""

    # 점수 척도가 코사인 유사도와 달라 chatbot/handoff.py 의 기준값(MIN_RETRIEVAL_SCORE)과 비교할
    # 수 없다. 그런 검색기는 calibrated=False 로 둔다 (챗봇은 '찾았는지'만 본다).
    calibrated = False

    def __init__(self, items: Iterable[tuple[Evidence, str]]):
        self.items = [(evidence, set(_tokens(text))) for evidence, text in items]
        df = Counter(token for _, tokens in self.items for token in tokens)
        n = len(self.items) or 1
        self.idf = {token: math.log(1 + n / count) for token, count in df.items()}

    def search(self, query: str, k: int = 5, where: dict[str, str] | None = None) -> list[Evidence]:
        query_tokens = set(_tokens(query)) & set(self.idf)
        total = sum(self.idf[t] for t in query_tokens)
        if not total:
            return []
        scored = []
        for evidence, tokens in self.items:
            if where and any(evidence.metadata.get(key) != value for key, value in where.items()):
                continue
            score = sum(self.idf[t] for t in query_tokens & tokens) / total
            if score > 0:
                scored.append((score, evidence))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [e.model_copy(update={"score": round(s, 4)}) for s, e in scored[:k]]


def keyword_docs(chunks: Iterable[Any] | None = None) -> KeywordRetriever:
    """data/raw/docs 절 단위 키워드 검색 (pipeline/chunking.py, CSA-18)."""
    if chunks is None:
        from cs_agent.pipeline.chunking import iter_doc_chunks

        chunks = iter_doc_chunks()
    items = []
    for chunk in chunks:
        metadata = {
            "doc_type": chunk.metadata.get("doc_type", ""),
            "product_code": chunk.metadata.get("product_code", ""),
            "family": chunk.metadata.get("family", ""),
            "doc_id": chunk.doc_id,
            "title": chunk.title,
        }
        evidence = Evidence(
            source="docs",
            doc_id=chunk.doc_id,
            section=chunk.section,
            text=chunk.text,
            metadata=metadata,
        )
        items.append((evidence, f"{chunk.metadata.get('title', '')} {chunk.title} {chunk.text}"))
    return KeywordRetriever(items)


@lru_cache(maxsize=1)
def _sections_by_doc() -> dict[str, tuple[Evidence, ...]]:
    sections: dict[str, list[Evidence]] = {}
    for evidence, _ in keyword_docs().items:
        sections.setdefault(evidence.doc_id, []).append(evidence)
    return {doc_id: tuple(items) for doc_id, items in sections.items()}


def doc_sections(doc_id: str) -> list[Evidence]:
    """한 문서의 절 전체 (data/raw/docs). 검색 결과와 상관없이 꼭 봐야 하는 정책 문서용.

    정책 문서(POL-*)는 짧고(2KB 안팎) 한국어 등 영어가 아닌 질문은 키워드 검색으로 못 찾는다.
    """
    return [e.model_copy(update={"score": 1.0}) for e in _sections_by_doc().get(doc_id, ())]


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def case_text(case: dict[str, str], final_reply: str) -> str:
    """사례 글 = 문의 요약 + 원인 + 조치 + 최종 답변 (embed_docs 적재와 같은 모양)."""
    parts = [
        ("Summary", case.get("case_summary") or case.get("symptom") or ""),
        ("Root cause", case.get("root_cause", "")),
        ("Action", case.get("action_taken", "")),
        ("Final reply", final_reply),
    ]
    return "\n".join(f"{label}: {value.strip()}" for label, value in parts if value.strip())


def _db_patterns() -> Retriever:
    """해결된 적 있는 패턴이 임베딩돼 있으면 pgvector 패턴 검색, 아니면 로컬 패턴 검색."""
    import sqlalchemy as sa

    from cs_agent.agents.case_patterns import PgPatternRetriever

    try:
        with _engine().connect() as conn:
            ready = conn.execute(
                sa.text(
                    "SELECT EXISTS (SELECT 1 FROM case_patterns p JOIN resolution_cases c "
                    "USING (pattern_id) WHERE p.embedding IS NOT NULL AND c.active)"
                )
            ).scalar()
    except Exception:  # case_patterns 가 아직 없음 (마이그레이션 전)
        ready = False
    return PgPatternRetriever() if ready else _memory_patterns()


# pgvector -----------------------------------------------------------------------------------

_TABLES = {
    "doc_chunks": {
        "columns": "id, doc_id, section, title, doc_type, product_code, family, text",
        "filters": DOC_FILTERS,
        "extra_where": "embedding IS NOT NULL",
        "source": "docs",
    },
    # 바꾸기 전 사례 검색 (지난 문의 글 임베딩). 운영은 패턴 DB 를 쓰고, 이것은
    # evaluation/case_retrieval.py 의 비교 기준으로만 남긴다.
    "resolution_cases": {
        "columns": "case_id, ticket_id, category, product_code, product_family, error_code, "
        "summary, cause, action, final_reply, cited",
        "filters": CASE_FILTERS,
        # active=false: 재문의로 다시 열린 사례 (db/models.py ResolutionCase)
        "extra_where": "embedding IS NOT NULL AND active",
        "source": "cases",
    },
}


@lru_cache
def _engine() -> Any:
    import sqlalchemy as sa

    return sa.create_engine(get_settings().database_url, pool_pre_ping=True)


@lru_cache(maxsize=256)  # 같은 문의 글을 docs · 패턴 · 지식 그래프가 한 번씩 찾는다
def _embed_query(text: str) -> tuple[float, ...]:
    from cs_agent.pipeline.embed_docs import embed  # 적재와 같은 모델·차원 (CSA-18)

    return tuple(embed([text])[0])


class PgVectorRetriever:
    """질문 임베딩과 코사인 거리가 가까운 행. score = 1 - 거리."""

    calibrated = True  # 문의 전환 기준값(MIN_RETRIEVAL_SCORE)을 이 점수로 쟀다

    def __init__(
        self,
        table: str,
        engine: Any = None,
        embed_fn: Callable[[str], Sequence[float]] = _embed_query,
    ):
        if table not in _TABLES:
            raise ValueError(f"unknown table: {table}")
        self.table = table
        self.config = _TABLES[table]
        self.engine = engine
        self.embed_fn = embed_fn

    def search(self, query: str, k: int = 5, where: dict[str, str] | None = None) -> list[Evidence]:
        import sqlalchemy as sa

        where = where or {}
        unknown = set(where) - set(self.config["filters"])
        if unknown:
            raise ValueError(f"{self.table} 에서 거를 수 없는 열: {sorted(unknown)}")
        clauses = [self.config["extra_where"]] + [f"{col} = :w_{col}" for col in where]
        sql = sa.text(
            f"SELECT {self.config['columns']}, embedding <=> CAST(:query AS vector) AS distance "
            f"FROM {self.table} WHERE {' AND '.join(clauses)} ORDER BY distance LIMIT :k"
        )
        params = {f"w_{col}": value for col, value in where.items()}
        params.update(query=str(list(self.embed_fn(query))), k=k)
        with (self.engine or _engine()).connect() as conn:
            rows = conn.execute(sql, params).mappings().all()
        return [self._evidence(row) for row in rows]

    def _evidence(self, row: Any) -> Evidence:
        score = round(1 - float(row["distance"]), 4)
        if self.config["source"] == "docs":
            metadata = {k: row[k] or "" for k in ("doc_type", "product_code", "family", "title")}
            metadata["doc_id"] = row["doc_id"]
            return Evidence(
                source="docs",
                doc_id=row["doc_id"],
                section=row["section"],
                text=row["text"],
                score=score,
                metadata=metadata,
            )
        case = {
            "case_summary": row["summary"] or "",
            "root_cause": row["cause"] or "",
            "action_taken": row["action"] or "",
        }
        cited = row["cited"] or []  # ["doc_id#section", ...] (embed_docs.case_rows)
        metadata = {
            k: row[k] or "" for k in ("category", "product_code", "error_code", "ticket_id")
        }
        metadata["family"] = row["product_family"] or ""
        metadata["reference_doc_id"] = cited[0].split("#", 1)[0] if cited else ""
        return Evidence(
            source="cases",
            doc_id=row["case_id"],
            text=case_text(case, row["final_reply"] or ""),
            score=score,
            metadata=metadata,
        )


def default_retrievers() -> tuple[Retriever, Retriever]:
    """(docs, cases) 검색기. 위 '할 일 3' 참고."""
    try:
        import sqlalchemy as sa

        settings = get_settings()
        if settings.gemini_api_key:  # 질문 임베딩에 키가 필요하다
            with _engine().connect() as conn:
                has_docs = conn.execute(
                    sa.text("SELECT EXISTS (SELECT 1 FROM doc_chunks WHERE embedding IS NOT NULL)")
                ).scalar()
            if has_docs:
                return PgVectorRetriever("doc_chunks"), _db_patterns()
    except Exception:  # DB 가 없거나 테이블이 아직 없음 → 로컬 대체 구현
        pass
    return keyword_docs(), _memory_patterns()


def _memory_patterns() -> Retriever:
    from cs_agent.agents.case_patterns import MemoryPatternRetriever, train_cases

    return MemoryPatternRetriever(train_cases())


# ④ 1차 검색 · ⑧ 근거 확정 ---------------------------------------------------------------------


@lru_cache
def _known_error_codes() -> frozenset[str]:
    from cs_agent.rules.tables import load_tables

    return frozenset(f["error_code"] for f in load_tables().faults if f.get("error_code"))


def _error_code_pattern(code: str) -> re.Pattern[str]:
    return re.compile(rf"(?<![\w.]){re.escape(code)}(?!\w)")


def find_error_codes(text: str, codes: Iterable[str] | None = None) -> list[str]:
    """원문에 나온 고장 카탈로그 에러코드 (CSA-19 fault_catalog.csv)."""
    codes = _known_error_codes() if codes is None else codes
    return sorted(code for code in codes if _error_code_pattern(code).search(text))


def _merge(groups: Iterable[list[Evidence]]) -> list[Evidence]:
    """같은 근거가 여러 번 나오면 점수가 높은 것만 남긴다."""
    best: dict[tuple, Evidence] = {}
    for evidence in (e for group in groups for e in group):
        key = (evidence.source, evidence.doc_id, evidence.section, evidence.text)
        if key not in best or evidence.score > best[key].score:
            best[key] = evidence
    return sorted(best.values(), key=lambda e: e.score, reverse=True)


def first_pass(docs: Retriever, cases: Retriever, text: str, k: int = DOCS_K) -> list[Evidence]:
    """④ 원문 기반 1차 검색."""
    groups = []
    if docs is not None:
        groups.append(docs.search(text, k))
        for code in find_error_codes(text):  # 에러코드가 있으면 TG 절을 따로 더 찾는다
            groups.append(docs.search(f"{code} {text}", ERROR_CODE_K, {"doc_type": "TG"}))
    if cases is not None:
        groups.append(cases.search(text, CASES_K))
    return _merge(groups)


def _matches_product(evidence: Evidence, extraction: Extraction) -> bool:
    """다른 제품(제품군)의 근거는 뺀다. 제품 구분이 없는 정책·FAQ 는 제품군만 본다."""
    product = evidence.metadata.get("product_code", "")
    family = evidence.metadata.get("family", "")
    if extraction.product_code and product and product != extraction.product_code:
        return False
    return not (extraction.product_family and family and family != extraction.product_family)


def _matches_pattern(evidence: Evidence, extraction: Extraction, codes: set[str]) -> bool:
    """패턴 근거: 적용 제품이 정해져 있으면 그 안에, 문의 에러코드가 후보에 있으면 같은 코드만."""
    applies = [p for p in evidence.metadata.get("applies_to", "").split(";") if p]
    if extraction.product_code and applies and extraction.product_code not in applies:
        return False
    code = (extraction.error_code or "").upper()
    own = evidence.metadata.get("error_code", "").upper()
    return not (code in codes and own and own != code)


def _is_preferred(evidence: Evidence, category: Category | None) -> bool:
    for preferred in PREFERRED_DOCS.get(category, ()) if category else ():
        if "-" in preferred and evidence.doc_id == preferred:
            return True
        if "-" not in preferred and evidence.metadata.get("doc_type") == preferred:
            return True
    return False


def _has_error_code(evidence: Evidence, code: str | None, category: Category | None) -> bool:
    if not code or evidence.metadata.get("doc_type") != "TG":
        return False
    if category and BUNDLE_OF.get(category) != Bundle.DIAGNOSIS:
        return False
    return bool(_error_code_pattern(code).search(evidence.metadata.get("title", "")))


def rerank_prompt(query: str, evidence: Evidence) -> str:
    title = evidence.metadata.get("title", "")
    return (
        "You rank knowledge-base sections for a B2B industrial-equipment customer-support team.\n\n"
        f"Customer inquiry:\n{query.strip()}\n\n"
        f"Section: {evidence.doc_id} {evidence.section or ''} {title}\n"
        f"{evidence.text[:RERANK_TEXT_CHARS]}\n\n"
        "Question: does this section contain the information an agent needs to answer this "
        "inquiry (the asked value, procedure, cause/fix, or policy)? Answer yes or no."
    )


def rerank_enabled(llm: Any) -> bool:
    settings = getattr(llm, "settings", None)
    return llm is not None and bool(getattr(settings, "rerank_enabled", False))


def relevance(llm: Any, query: str, evidence: list[Evidence]) -> list[float] | None:
    """절마다 관련도 0~1 (yes 확신도). LLM 꺼짐(fake)·호출 실패면 None (규칙 정렬 그대로)."""
    if not evidence:
        return []

    def judge(e: Evidence) -> Any:
        return llm.judge(RERANK_TASK, rerank_prompt(query, e), ["yes", "no"])

    trace_context = contextvars.copy_context()  # 문의 단위 Langfuse trace 를 스레드에도
    try:
        with ThreadPoolExecutor(min(RERANK_WORKERS, len(evidence))) as pool:
            results = list(pool.map(lambda e: trace_context.copy().run(judge, e), evidence))
    except Exception:
        _LOGGER.exception("reranker 판단 실패 → 규칙 정렬 그대로")
        return None
    if any(r.model == "fake" for r in results):
        return None
    return [r.confidence if r.answer == "yes" else 1.0 - r.confidence for r in results]


def rerank(
    ranked: list[Evidence],
    query: str,
    llm: Any,
    *,
    pinned: set[tuple[str, str | None]] = frozenset(),
    weight: float | None = None,
    scores: list[float] | None = None,
) -> list[Evidence]:
    """규칙 정렬된 docs 위 RERANK_POOL 개를 관련도로 다시 정렬. pinned(에러코드 정확 일치)는 위에.

    scores 를 주면 판단 모델을 다시 부르지 않는다 (K3 비교에서 가중치만 바꿔 볼 때).
    """
    pool, rest = ranked[:RERANK_POOL], ranked[RERANK_POOL:]
    if not query or len(pool) < 2:
        return ranked
    if scores is None:
        scores = relevance(llm, query, pool)
    if scores is None:
        return ranked
    if weight is None:
        weight = llm.settings.rerank_weight
    rescored = [
        e.model_copy(
            update={
                "score": round(e.score + weight * r, 4),
                "metadata": {**e.metadata, "rerank": f"{r:.3f}"},
            }
        )
        for e, r in zip(pool, scores, strict=True)
    ]
    rescored.sort(key=lambda e: ((e.doc_id, e.section) in pinned, e.score), reverse=True)
    return rescored + rest


def finalize_evidence(
    candidates: list[Evidence],
    extraction: Extraction,
    k: int = 3,
    category: Category | None = None,
    *,
    graph: Any = None,
    query: str = "",
    llm: Any = None,
) -> list[Evidence]:
    """⑧ 제품·유형으로 거르고 재정렬한 확정 근거. docs k개 + cases FINAL_CASES_K개.

    graph(agents/knowledge_graph.KnowledgeGraph)가 있으면 사례는 지식 그래프에서 찾는다 (CSA-71).
    그래프가 실패하면 후보의 패턴 DB 사례로 대체한다.
    llm(LLMRouter)과 query 를 주고 RERANK_ENABLED 면 docs 를 reranker 로 다시 정렬한다 (CSA-81).
    """
    docs: dict[tuple[str, str | None], Evidence] = {}
    pinned: set[tuple[str, str | None]] = set()
    for evidence in candidates:
        if evidence.source != "docs" or not _matches_product(evidence, extraction):
            continue
        score = evidence.score
        if _is_preferred(evidence, category):
            score += TYPE_BONUS
        key = (evidence.doc_id, evidence.section)  # 긴 절을 나눈 조각은 한 번만
        if _has_error_code(evidence, extraction.error_code, category):
            score += ERROR_CODE_BONUS
            pinned.add(key)
        if key not in docs or score > docs[key].score:
            docs[key] = evidence.model_copy(update={"score": round(score, 4)})

    ranked = sorted(docs.values(), key=lambda e: e.score, reverse=True)
    if rerank_enabled(llm):
        ranked = rerank(ranked, query, llm, pinned=pinned)
    if graph is not None:
        try:
            return ranked[:k] + graph.search(query, extraction, category, FINAL_CASES_K)
        except Exception:  # Neo4j 장애·임베딩 실패 → 패턴 DB (처리 흐름은 멈추지 않는다)
            _LOGGER.exception("지식 그래프 사례 검색 실패 → 패턴 DB 로 대체")

    cases = [e for e in candidates if e.source == "cases" and _matches_product(e, extraction)]
    codes = {e.metadata.get("error_code", "").upper() for e in cases} - {""}
    cases = [e for e in cases if _matches_pattern(e, extraction, codes)]
    if category:  # 같은 유형 사례를 먼저
        cases.sort(key=lambda e: (e.metadata.get("category") == category, e.score), reverse=True)
    return ranked[:k] + cases[:FINAL_CASES_K]


# K3 측정 -------------------------------------------------------------------------------------


def k3_hit(evidence: list[Evidence], reference_doc_id: str, reference_section: str) -> bool:
    """정답 문서(절이 있으면 절까지)가 확정 근거 docs 안에 있는가."""
    return any(
        e.source == "docs"
        and e.doc_id == reference_doc_id
        and (not reference_section or e.section == reference_section)
        for e in evidence
    )


def measure_k3(
    tickets: Iterable[dict[str, str]], docs: Retriever, cases: Retriever
) -> dict[str, Any]:
    """tickets 의 정답 유형·제품·에러코드로 근거를 확정해 K3 를 잰다 (검색만 따로 잰다)."""
    total = hits = 0
    by_category: dict[str, list[int]] = {}
    for row in tickets:
        if not row["reference_doc_id"]:
            continue
        text = f"{row['inquiry_subject']}\n{row['inquiry_body']}"
        extraction = Extraction(
            product_code=row["product_code"] or None,
            product_family=row["product_family"] or None,
            error_code=row["error_code_reported"] or None,
        )
        category = Category(row["category_code"])
        evidence = finalize_evidence(first_pass(docs, cases, text), extraction, category=category)
        hit = k3_hit(evidence, row["reference_doc_id"], row["reference_section"])
        total += 1
        hits += hit
        counts = by_category.setdefault(row["category_code"], [0, 0])
        counts[0] += hit
        counts[1] += 1
    return {
        "total": total,
        "hits": hits,
        "k3": hits / total if total else 0.0,
        "by_category": by_category,
    }


def measure_rerank(
    tickets: Iterable[dict[str, str]],
    docs: Retriever,
    cases: Retriever,
    llm: Any,
    weights: Sequence[float] = (0.3, 0.5, 1.0, 2.0),
    k: int = 3,
) -> dict[str, Any]:
    """reranker 끔/켬 K3 비교. 같은 후보·같은 판단으로 가중치만 바꿔 본다 (판단은 문의당 1번).

    정답 절이 규칙 정렬 위 RERANK_POOL 안에 없으면 reranker 로도 못 올리므로 pool_hits 도 같이 낸다.
    """
    total = base_hits = pool_hits = failed = 0
    hits = dict.fromkeys(weights, 0)
    by_category: dict[str, dict[str, int]] = {}
    changed: list[dict[str, str]] = []
    for row in tickets:
        if not row["reference_doc_id"]:
            continue
        text = f"{row['inquiry_subject']}\n{row['inquiry_body']}"
        extraction = Extraction(
            product_code=row["product_code"] or None,
            product_family=row["product_family"] or None,
            error_code=row["error_code_reported"] or None,
        )
        category = Category(row["category_code"])
        candidates = first_pass(docs, cases, text)
        pool = [
            e
            for e in finalize_evidence(candidates, extraction, k=RERANK_POOL, category=category)
            if e.source == "docs"
        ]
        pinned = {
            (e.doc_id, e.section)
            for e in pool
            if _has_error_code(e, extraction.error_code, category)
        }
        ref = (row["reference_doc_id"], row["reference_section"])
        base = k3_hit(pool[:k], *ref)
        scores = relevance(llm, text, pool)
        if scores is None:
            failed += 1
        total += 1
        base_hits += base
        pool_hits += k3_hit(pool, *ref)
        counts = by_category.setdefault(row["category_code"], {"n": 0, "base": 0})
        counts["n"] += 1
        counts["base"] += base
        for w in weights:
            after = (
                rerank(pool, text, llm, pinned=pinned, weight=w, scores=scores)
                if scores is not None
                else pool
            )
            hit = k3_hit(after[:k], *ref)
            hits[w] += hit
            counts[str(w)] = counts.get(str(w), 0) + hit
            if w == weights[0] and hit != base:
                changed.append({"ticket_id": row.get("ticket_id", ""), "gain": str(hit - base)})
    return {
        "total": total,
        "base": base_hits,
        "pool": pool_hits,
        "failed": failed,
        "rerank": hits,
        "by_category": by_category,
        "changed": changed,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="근거 일치율 K3 측정")
    parser.add_argument("--split", default="valid", choices=("train", "valid", "test"))
    parser.add_argument(
        "--rerank", action="store_true", help="reranker 끔/켬 비교 (LLM_PROVIDER=live 필요, CSA-81)"
    )
    parser.add_argument("--limit", type=int, default=0, help="앞 N건만 (0 이면 전부)")
    args = parser.parse_args()

    docs, cases = default_retrievers()
    rows = [
        r
        for r in _read_csv(get_settings().raw_data_dir / "tickets.csv")
        if r["data_split"] == args.split and r["reference_doc_id"]
    ]
    if args.limit:
        rows = rows[: args.limit]
    print(f"retriever={type(docs).__name__} split={args.split}")
    if not args.rerank:
        result = measure_k3(rows, docs, cases)
        print(f"K3 = {result['hits']}/{result['total']} ({result['k3']:.1%})")
        for category, (hit, n) in sorted(result["by_category"].items()):
            print(f"  {category:<11} {hit}/{n} ({hit / n:.1%})")
        return

    from cs_agent.llm.router import get_router

    llm = get_router()
    if not llm.enabled:
        raise SystemExit("--rerank 는 LLM_PROVIDER=live 와 판단 모델 키가 필요하다")
    weights = (0.3, 0.5, 1.0, 2.0)
    started = time.perf_counter()
    result = measure_rerank(rows, docs, cases, llm, weights)
    elapsed = time.perf_counter() - started
    n = result["total"]
    print(f"문의 {n}건 · 판단 실패 {result['failed']}건 · {elapsed:.0f}초 ({elapsed / n:.1f}초/건)")
    print(
        f"정답 절이 rerank 후보(위 {RERANK_POOL}) 안: "
        f"{result['pool']}/{n} ({result['pool'] / n:.1%})"
    )
    print(f"K3 끔            = {result['base']}/{n} ({result['base'] / n:.1%})")
    for w, hit in result["rerank"].items():
        print(f"K3 켬 weight={w:<4} = {hit}/{n} ({hit / n:.1%})  {hit - result['base']:+d}")
    print("유형별 (끔 → 켬 weight 별)")
    for category, c in sorted(result["by_category"].items()):
        after = " ".join(f"{c[str(w)]}" for w in weights)
        print(f"  {category:<11} n={c['n']:<4} 끔 {c['base']:<4} 켬 {after}")


if __name__ == "__main__":
    main()
