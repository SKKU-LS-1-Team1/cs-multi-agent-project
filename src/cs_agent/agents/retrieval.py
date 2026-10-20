# 지식 검색 에이전트 — ④ 1차 검색 · ⑧ 근거 확정 (CSA-28 · 담당 박종석 · Sprint 1)
#
# 답변 작성(⑨)과 챗봇(CSA-32)이 함께 쓴다. 벡터 검색은 PostgreSQL + pgvector (기획서 7.1, 팀장 확정:
# ChromaDB 대신). 검색 대상 2개:
# - `docs` = doc_chunks 테이블: 공식 문서·FAQ·정책을 절 단위로 (CSA-18에서 적재). 값·절차·정책의
#     근거. 값이 충돌하면 이쪽.
# - `cases` = resolution_cases 테이블(embedding 열): 해결 사례 (train 연결 + 운영 중 해결 건,
#     searchable=true 인 것만). 비슷한 문의를 어떻게 풀었는지, 문장 본보기. 참고로만.
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
#    docs top-8 + cases top-3 정도.
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
# - 키워드 대체 구현의 cases 는 data/raw 의 사례 중 train 티켓에 연결된 것만 쓴다 (완료 기준 2).
# - K3 측정: uv run python -m cs_agent.agents.retrieval --split valid
import argparse
import csv
import math
import re
from collections import Counter
from collections.abc import Callable, Iterable, Sequence
from functools import lru_cache
from pathlib import Path
from typing import Any, Protocol

from cs_agent.config import get_settings
from cs_agent.domain import BUNDLE_OF, Bundle, Category
from cs_agent.schemas import Evidence, Extraction

DOCS_K = 8
CASES_K = 3
FINAL_CASES_K = 2
ERROR_CODE_K = 3
TYPE_BONUS = 0.3  # 유형에 맞는 문서 종류
ERROR_CODE_BONUS = 1.0  # 절 제목이 문의의 에러코드와 같은 TG 절 (정확 조회라 가장 우선)

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


def keyword_cases(raw_dir: Path | None = None) -> KeywordRetriever:
    """data/raw 의 해결 사례 중 train 티켓에 연결된 것만 (test·valid 사례는 검색 대상이 아니다)."""
    raw_dir = raw_dir or get_settings().raw_data_dir
    tickets = {t["ticket_id"]: t for t in _read_csv(raw_dir / "tickets.csv")}
    items = []
    for case in _read_csv(raw_dir / "resolution_cases.csv"):
        ticket = tickets.get(case["ticket_id"])
        if not ticket or ticket["data_split"] != "train":
            continue
        text = case_text(case, ticket.get("final_reply", ""))
        evidence = Evidence(
            source="cases",
            doc_id=case["case_id"],
            text=text,
            metadata={
                "category": case["category_code"],
                "product_code": case["product_code"],
                "family": case["product_family"],
                "error_code": case["error_code"],
                "ticket_id": case["ticket_id"],
                "reference_doc_id": case["reference_doc_id"],
            },
        )
        items.append((evidence, text))
    return KeywordRetriever(items)


# pgvector -----------------------------------------------------------------------------------

_TABLES = {
    "doc_chunks": {
        "columns": "id, doc_id, section, title, doc_type, product_code, family, text",
        "filters": DOC_FILTERS,
        "extra_where": "embedding IS NOT NULL",
        "source": "docs",
    },
    "resolution_cases": {
        "columns": "case_id, ticket_id, category, product_code, error_code, summary, cause, "
        "action_taken, final_reply, reference_doc_id",
        "filters": CASE_FILTERS,
        "extra_where": "embedding IS NOT NULL AND searchable",
        "source": "cases",
    },
}


@lru_cache
def _engine() -> Any:
    import sqlalchemy as sa

    return sa.create_engine(get_settings().database_url, pool_pre_ping=True)


def _embed_query(text: str) -> list[float]:
    from cs_agent.pipeline.embed_docs import embed  # 적재와 같은 모델·차원 (CSA-18)

    return embed([text])[0]


class PgVectorRetriever:
    """질문 임베딩과 코사인 거리가 가까운 행. score = 1 - 거리."""

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
            "action_taken": row["action_taken"] or "",
        }
        keys = ("category", "product_code", "error_code", "ticket_id", "reference_doc_id")
        return Evidence(
            source="cases",
            doc_id=row["case_id"],
            text=case_text(case, row["final_reply"] or ""),
            score=score,
            metadata={k: row[k] or "" for k in keys},
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
                return PgVectorRetriever("doc_chunks"), PgVectorRetriever("resolution_cases")
    except Exception:  # DB 가 없거나 테이블이 아직 없음 → 로컬 대체 구현
        pass
    return keyword_docs(), keyword_cases()


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


def finalize_evidence(
    candidates: list[Evidence],
    extraction: Extraction,
    k: int = 3,
    category: Category | None = None,
) -> list[Evidence]:
    """⑧ 제품·유형으로 거르고 재정렬한 확정 근거. docs k개 + cases FINAL_CASES_K개."""
    docs: dict[tuple[str, str | None], Evidence] = {}
    for evidence in candidates:
        if evidence.source != "docs" or not _matches_product(evidence, extraction):
            continue
        score = evidence.score
        if _is_preferred(evidence, category):
            score += TYPE_BONUS
        if _has_error_code(evidence, extraction.error_code, category):
            score += ERROR_CODE_BONUS
        key = (evidence.doc_id, evidence.section)  # 긴 절을 나눈 조각은 한 번만
        if key not in docs or score > docs[key].score:
            docs[key] = evidence.model_copy(update={"score": round(score, 4)})

    cases = [e for e in candidates if e.source == "cases" and _matches_product(e, extraction)]
    if category:  # 같은 유형 사례를 먼저
        cases.sort(key=lambda e: (e.metadata.get("category") == category, e.score), reverse=True)
    ranked = sorted(docs.values(), key=lambda e: e.score, reverse=True)
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


def main() -> None:
    parser = argparse.ArgumentParser(description="근거 일치율 K3 측정")
    parser.add_argument("--split", default="valid", choices=("train", "valid", "test"))
    args = parser.parse_args()

    docs, cases = default_retrievers()
    rows = [
        r
        for r in _read_csv(get_settings().raw_data_dir / "tickets.csv")
        if r["data_split"] == args.split
    ]
    result = measure_k3(rows, docs, cases)
    print(f"retriever={type(docs).__name__} split={args.split}")
    print(f"K3 = {result['hits']}/{result['total']} ({result['k3']:.1%})")
    for category, (hit, n) in sorted(result["by_category"].items()):
        print(f"  {category:<11} {hit}/{n} ({hit / n:.1%})")


if __name__ == "__main__":
    main()
