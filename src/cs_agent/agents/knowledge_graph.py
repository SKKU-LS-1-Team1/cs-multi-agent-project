# 사례 학습 지식 그래프 — ⑧ 근거 확정의 사례 검색 · 해결 확정 학습 (CSA-71 · CSA-72 · 김동규)
# 설계안: https://claude.ai/artifact/NhXpbnwscYFvyCW2PzoaeB · 적재: pipeline/build_graph.py (CSA-70)
#
# 멘토링 피드백 "그래프 DB 를 쓰자 · 사례 학습은 지식 그래프로 · 임베딩은 유사도 왜곡이 있다"에
# 대한 답. 사례 후보를 그래프 경로(제품 → 고장 ← 에러코드)로 먼저 좁히고, 임베딩은 남은 후보 안에서
# 증상 비교에만 쓴다. 따라간 경로를 근거 메타데이터(graph_path)로 남겨 화면에 보여 준다.
#
# 검색 (search — retrieval.finalize_evidence 의 사례 자리, GRAPH_ENABLED=true 일 때)
#   1. 추출된 제품에 APPLIES_TO 로 연결된 Fault 만 후보. 제품이 없으면(또는 연결된 고장이 없으면)
#      제품군(Product-IN_FAMILY->Family)으로 넓힌다. 둘 다 없으면 전체 (벡터 인덱스).
#   2. 에러코드가 있으면 SHOWS_CODE 로 더 좁힌다 (좁힌 결과가 비면 코드는 무시 — 오타·다른 코드).
#   3. 후보 중 해결된 적 있는(active 사례가 있는) 고장만, 문의 임베딩 ↔ 패턴 설명 임베딩 코사인으로
#      위 2개 (retrieval.FINAL_CASES_K).
#   4. 고장마다 대표 Case(운영 사례 → 같은 제품 사례 → 최근 해결 순)와 DocSection(대표 사례가 인용한
#      절, 없으면 이 고장 사례들이 많이 인용한 절)을
#      붙여 Evidence(source="cases") 로 돌려준다. 글 모양은 패턴 DB 와 같다
#      (case_patterns.pattern_evidence) — 초안 작성(⑨)·평가 집계가 그대로 쓴다.
#   그래프가 꺼져 있거나 접속·임베딩이 실패하면 finalize_evidence 가 지금의 패턴 DB 경로로 대체한다.
# 학습 (learn / deactivate — case_memory.with_graph_learning 이 records 에 붙인다, CSA-72)
#   - 해결 확정(services/tickets.resolve → records.save_case) 때 Case 를 MERGE 하고 INSTANCE_OF ·
#     ON_PRODUCT · CITED 로 잇는다 (인용한 절은 고장의 EXPLAINED_IN 에도 — 적재와 같은 규칙).
#   - 카탈로그에 없는 원인이면 LIVE-… Fault 를 새로 만들고 설명을 임베딩한다.
#   - 재문의로 다시 열린 사례는 active=false → 대표 사례 · 해결 건수(case_count)에서 빠진다.
#   - 그래프 쓰기가 실패해도 해결 확정은 막지 않는다 (DB 가 원본, build_graph 를 다시 돌리면
#     맞춰진다).
#
# 저장소는 GraphStore 규약으로 나눈다: Neo4jStore(운영) / tests/stubs.MemoryGraph(테스트 fake,
# 같은 GraphData 로 만든다). 검색 · 학습 규칙은 KnowledgeGraph 하나에만 있다.
import logging
from collections.abc import Callable, Mapping, Sequence
from typing import Any, Protocol

from cs_agent.agents.case_patterns import LIVE_PREFIX, pattern_evidence, pattern_row
from cs_agent.config import Settings, get_settings
from cs_agent.schemas import Evidence, Extraction

_LOGGER = logging.getLogger(__name__)

FINAL_K = 2  # retrieval.FINAL_CASES_K 와 같다
GLOBAL_CANDIDATES = 50  # 제품 · 제품군을 모를 때 벡터 인덱스에서 먼저 가져올 수
PATH_SEP = " → "


class GraphStore(Protocol):
    def faults_on_product(self, product_code: str) -> set[str]: ...

    def faults_in_family(self, family: str) -> set[str]: ...

    def faults_with_code(self, code: str) -> set[str]: ...

    def rank(
        self, fault_ids: set[str] | None, vector: Sequence[float], k: int
    ) -> list[tuple[str, float]]:
        """해결된 적 있는 고장만, 코사인 유사도(-1~1) 높은 순. fault_ids=None 이면 전체."""
        ...

    def details(self, fault_ids: Sequence[str]) -> dict[str, dict]:
        """고장 → {"pattern": 패턴 행, "cases": active 사례(대표 먼저), "sections": 절 id}."""
        ...

    def has_vector(self, fault_id: str) -> bool: ...

    def learn(self, case: Mapping[str, Any], fault: Mapping[str, Any] | None) -> None:
        """사례를 MERGE 하고 잇는다. fault 가 있으면 없을 때 만든다 (LIVE 패턴)."""
        ...

    def deactivate(self, ticket_id: str) -> None: ...


def graph_path(
    extraction: Extraction,
    scope: str | None,
    code: str | None,
    fault_id: str,
    case_id: str,
    section: str | None,
) -> str:
    """제품(또는 제품군) → 에러코드 → 고장 → 사례 → 문서 절."""
    start = extraction.product_code if scope == "product" else extraction.product_family
    parts = [start if scope else None, code, fault_id, case_id, section]
    return PATH_SEP.join(p for p in parts if p)


class KnowledgeGraph:
    def __init__(
        self, store: GraphStore, embed_fn: Callable[[str], Sequence[float]] | None = None
    ) -> None:
        self.store = store
        self.embed_fn = embed_fn

    def _embed(self, text: str) -> Sequence[float]:
        if self.embed_fn is not None:
            return self.embed_fn(text)
        from cs_agent.agents.retrieval import _embed_query

        return _embed_query(text)

    # 검색 ---------------------------------------------------------------------------------------

    def candidates(self, extraction: Extraction) -> tuple[set[str] | None, str | None, str | None]:
        """(후보 고장, 출발점 product|family|None, 좁힌 에러코드)."""
        ids: set[str] | None = None
        scope = None
        if extraction.product_code:
            ids = self.store.faults_on_product(extraction.product_code) or None
            scope = "product" if ids else None
        if ids is None and extraction.product_family:
            ids = self.store.faults_in_family(extraction.product_family) or None
            scope = "family" if ids else None
        code = (extraction.error_code or "").strip().upper() or None
        if code:
            with_code = self.store.faults_with_code(code)
            narrowed = with_code if ids is None else ids & with_code
            if narrowed:
                ids = narrowed
            else:
                code = None
        return ids, scope, code

    def search(
        self, query: str, extraction: Extraction, category: Any = None, k: int = FINAL_K
    ) -> list[Evidence]:
        ids, scope, code = self.candidates(extraction)
        ranked = self.store.rank(ids, self._embed(query), k)
        details = self.store.details([fid for fid, _ in ranked])
        results = []
        for fault_id, score in ranked:
            found = details.get(fault_id)
            if not found or not found["cases"]:
                continue
            # 저장소 순서(운영 사례 → 최근 해결)를 지키면서 같은 제품 사례(ON_PRODUCT)를 앞으로
            cases = sorted(
                found["cases"],
                key=lambda c: (
                    c.get("data_split") == "live",
                    bool(extraction.product_code)
                    and c.get("product_code") == extraction.product_code,
                ),
                reverse=True,
            )
            example = cases[0]
            # 대표 사례가 인용한 절을 먼저, 없으면 이 고장 사례들이 많이 인용한 절
            sections = [s for s in example.get("cited") or [] if s in found["sections"]]
            section = (sections or found["sections"] or [None])[0]
            evidence = pattern_evidence(found["pattern"], cases, round(score, 4))
            doc_id, _, number = (section or "").partition("#")
            path = graph_path(extraction, scope, code, fault_id, example["case_id"], section)
            evidence.metadata.update(
                retriever="graph",
                graph_path=path,
                graph_scope=scope or "all",
                reference_doc_id=doc_id,
                reference_section=number,
            )
            if section:
                evidence.text += f"\nReference: {doc_id} §{number}" if number else f"\n{doc_id}"
            results.append(evidence)
        return results

    # 학습 ---------------------------------------------------------------------------------------

    def learn(self, case: Mapping[str, Any]) -> None:
        """해결 확정 사례 → Case 노드 (카탈로그에 없는 원인이면 LIVE 고장 노드도)."""
        from cs_agent.pipeline.build_graph import fault_node

        pattern = pattern_row(case)
        fault = None
        if pattern is not None and pattern["pattern_id"].startswith(LIVE_PREFIX):
            fault = fault_node(pattern)
            if not self.store.has_vector(pattern["pattern_id"]):
                try:
                    fault["embedding"] = list(self._embed(pattern["text"]))
                except Exception:  # 벡터 없이 두면 검색에 안 오를 뿐 — build_graph 가 채운다
                    _LOGGER.exception("LIVE 고장 설명 임베딩 실패 — 벡터 없이 저장")
        self.store.learn({**case, "pattern_id": pattern and pattern["pattern_id"]}, fault)

    def deactivate(self, ticket_id: str) -> None:
        self.store.deactivate(ticket_id)


# Neo4j ------------------------------------------------------------------------------------------


def _cosine(normalized: float) -> float:
    """Neo4j 코사인 점수는 (1 + cos) / 2 로 0~1 이다. pgvector(1 - 거리)와 같은 척도로 되돌린다."""
    return 2 * float(normalized) - 1


class Neo4jStore:
    _LEARNED = "EXISTS { (:Case {active: true})-[:INSTANCE_OF]->(f) }"
    _DETAILS = """
        MATCH (f:Fault) WHERE f.id IN $ids
        CALL (f) {
            OPTIONAL MATCH (c:Case {active: true})-[:INSTANCE_OF]->(f)
            WITH c ORDER BY c.split = 'live' DESC, c.resolved_at DESC, c.id DESC
            RETURN collect(c {case_id: c.id, .final_reply, data_split: c.split, .product_code,
                              cited: [(c)-[:CITED]->(d:DocSection) | d.id]}) AS cases
        }
        CALL (f) {
            OPTIONAL MATCH (f)-[:EXPLAINED_IN]->(d:DocSection)
            WITH d, size([(c:Case {active: true})-[:INSTANCE_OF]->(f) WHERE (c)-[:CITED]->(d)
                          | c]) AS n
            ORDER BY n DESC, d.id
            RETURN collect(d.id) AS sections
        }
        RETURN f {pattern_id: f.id, .family, .error_code, .applies_to, .text} AS pattern,
               cases, sections
    """

    def __init__(self, driver: Any) -> None:
        self.driver = driver

    def _read(self, query: str, **params: Any) -> list[dict]:
        with self.driver.session() as session:
            return [record.data() for record in session.run(query, params)]

    def _ids(self, query: str, **params: Any) -> set[str]:
        return {r["id"] for r in self._read(query, **params)}

    def faults_on_product(self, product_code: str) -> set[str]:
        return self._ids(
            "MATCH (f:Fault)-[:APPLIES_TO]->(:Product {id: $p}) RETURN f.id AS id", p=product_code
        )

    def faults_in_family(self, family: str) -> set[str]:
        return self._ids(
            "MATCH (f:Fault)-[:APPLIES_TO]->(:Product)-[:IN_FAMILY]->(:Family {id: $f}) "
            "RETURN DISTINCT f.id AS id",
            f=family,
        )

    def faults_with_code(self, code: str) -> set[str]:
        return self._ids(
            "MATCH (f:Fault)-[:SHOWS_CODE]->(:ErrorCode {id: $c}) RETURN f.id AS id", c=code
        )

    def rank(
        self, fault_ids: set[str] | None, vector: Sequence[float], k: int
    ) -> list[tuple[str, float]]:
        from cs_agent.pipeline.build_graph import VECTOR_INDEX

        vector = [float(x) for x in vector]
        if fault_ids is None:
            rows = self._read(
                f"CALL db.index.vector.queryNodes('{VECTOR_INDEX}', $n, $v) YIELD node AS f, score "
                f"WHERE {self._LEARNED} RETURN f.id AS id, score ORDER BY score DESC, id LIMIT $k",
                n=GLOBAL_CANDIDATES,
                v=vector,
                k=k,
            )
        else:
            rows = self._read(
                "MATCH (f:Fault) WHERE f.id IN $ids AND f.embedding IS NOT NULL "
                f"AND {self._LEARNED} "
                "WITH f, vector.similarity.cosine(f.embedding, $v) AS score "
                "RETURN f.id AS id, score ORDER BY score DESC, id LIMIT $k",
                ids=sorted(fault_ids),
                v=vector,
                k=k,
            )
        return [(r["id"], _cosine(r["score"])) for r in rows]

    def details(self, fault_ids: Sequence[str]) -> dict[str, dict]:
        if not fault_ids:
            return {}
        rows = self._read(self._DETAILS, ids=list(fault_ids))
        return {r["pattern"]["pattern_id"]: r for r in rows}

    def has_vector(self, fault_id: str) -> bool:
        return bool(
            self._read(
                "MATCH (f:Fault {id: $id}) WHERE f.embedding IS NOT NULL RETURN f.id AS id",
                id=fault_id,
            )
        )

    def learn(self, case: Mapping[str, Any], fault: Mapping[str, Any] | None) -> None:
        from cs_agent.pipeline.build_graph import case_node, refresh_case_counts

        node = case_node(case)
        with self.driver.session() as session:
            if fault is not None:
                session.run(
                    "MERGE (f:Fault {id: $f.id}) ON CREATE SET f += $f "
                    "SET f.embedding = coalesce(f.embedding, $f.embedding) "
                    "WITH f UNWIND $f.applies_to AS p MATCH (prod:Product {id: p}) "
                    "MERGE (f)-[:APPLIES_TO]->(prod)",
                    f=dict(fault),
                )
                if fault.get("error_code"):
                    session.run(
                        "MATCH (f:Fault {id: $id}) MERGE (e:ErrorCode {id: $code}) "
                        "MERGE (f)-[:SHOWS_CODE]->(e)",
                        id=fault["id"],
                        code=fault["error_code"],
                    )
            session.run(
                "MERGE (c:Case {id: $c.id}) SET c += $c "
                "WITH c OPTIONAL MATCH (c)-[r:INSTANCE_OF|ON_PRODUCT|CITED]->() DELETE r",
                c=node,
            )
            session.run(
                "MATCH (c:Case {id: $id}) "
                "OPTIONAL MATCH (f:Fault {id: $fault}) "
                "OPTIONAL MATCH (p:Product {id: $product}) "
                "FOREACH (_ IN CASE WHEN f IS NULL THEN [] ELSE [1] END | "
                "  MERGE (c)-[:INSTANCE_OF]->(f)) "
                "FOREACH (_ IN CASE WHEN p IS NULL THEN [] ELSE [1] END | "
                "  MERGE (c)-[:ON_PRODUCT]->(p)) "
                "WITH c, f UNWIND $cited AS sid MATCH (d:DocSection {id: sid}) "
                "MERGE (c)-[:CITED]->(d) "
                "FOREACH (_ IN CASE WHEN f IS NULL THEN [] ELSE [1] END | "
                "  MERGE (f)-[:EXPLAINED_IN]->(d))",
                id=node["id"],
                fault=case.get("pattern_id"),
                product=node["product_code"],
                cited=list(case.get("cited") or []),
            )
            refresh_case_counts(session)

    def deactivate(self, ticket_id: str) -> None:
        from cs_agent.pipeline.build_graph import refresh_case_counts

        with self.driver.session() as session:
            session.run("MATCH (c:Case {ticket_id: $t}) SET c.active = false", t=ticket_id)
            refresh_case_counts(session)


def connect(settings: Settings | None = None) -> Any:
    """Neo4j 드라이버 (extra: graph). 붙는지 바로 확인한다."""
    from neo4j import GraphDatabase

    settings = settings or get_settings()
    driver = GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
        connection_timeout=5,
    )
    try:
        driver.verify_connectivity()
    except Exception:
        driver.close()
        raise
    return driver


def default_graph(enabled: bool | None = None) -> KnowledgeGraph | None:
    """GRAPH_ENABLED 이고 Neo4j 에 붙으면 지식 그래프, 아니면 None (패턴 DB 로 찾는다)."""
    settings = get_settings()
    if not (settings.graph_enabled if enabled is None else enabled):
        return None
    try:
        driver = connect(settings)
    except Exception as e:  # 드라이버 없음 · 접속 실패 → 처리 흐름은 패턴 DB 로
        _LOGGER.warning("지식 그래프 연결 실패 → 패턴 DB 로 사례를 찾는다: %s", e)
        return None
    return KnowledgeGraph(Neo4jStore(driver))


def close(graph: KnowledgeGraph | None) -> None:
    driver = getattr(getattr(graph, "store", None), "driver", None)
    if driver is not None:
        driver.close()
