# 사례 학습 지식 그래프 (CSA-70 적재 · CSA-71 검색 · CSA-72 학습).
# Neo4j 없이 tests/stubs.MemoryGraph 로 돈다.
import pytest
from fastapi.testclient import TestClient
from stubs import ANALYSIS, graph_data, memory_graph, toy_embed

from cs_agent.agents import knowledge_graph
from cs_agent.agents.case_memory import GraphLearningRecords, with_graph_learning
from cs_agent.agents.knowledge_graph import KnowledgeGraph, _cosine
from cs_agent.agents.retrieval import finalize_evidence
from cs_agent.config import Settings
from cs_agent.llm.router import LLMRouter
from cs_agent.main import create_app
from cs_agent.pipeline.build_graph import build, csv_cases
from cs_agent.schemas import Evidence, Extraction

S100 = "INV-LSLV0075-S100"
QUERY = (
    "Inverter trips with over-current immediately at run command. "
    "Motor cable insulation may be damaged, megger test planned."
)
EOC = Extraction(product_code=S100, product_family="DRIVE", error_code="E.OC")


@pytest.fixture
def graph() -> KnowledgeGraph:
    return KnowledgeGraph(memory_graph(), embed_fn=toy_embed)


# 적재 (CSA-70) -----------------------------------------------------------------------------------


def test_graph_counts_match_reference_tables():
    counts = graph_data().counts()
    expected = {"Product": 23, "Fault": 97, "ErrorCode": 45, "Part": 19, "Firmware": 39}
    assert {k: counts[k] for k in expected} == expected
    assert counts["Case"] == 568 and counts["Family"] == 11
    assert counts["APPLIES_TO"] == 156  # 고장 카탈로그 applies_to 전체
    assert counts["INSTANCE_OF"] == counts["CITED"] == 568  # 모든 train 사례가 고장·절에 이어진다


def test_graph_build_is_repeatable():
    first, second = build(csv_cases(), {}), build(csv_cases(), {})
    assert first.nodes == second.nodes and first.rels == second.rels


# 검색 (CSA-71) -----------------------------------------------------------------------------------


def test_candidates_follow_product_then_family_and_error_code(graph):
    on_product, scope, code = graph.candidates(EOC)
    assert (scope, code) == ("product", "E.OC")
    assert on_product == graph.store.faults_on_product(S100) & graph.store.faults_with_code("E.OC")

    # 그래프에 없는 제품 → 제품군으로 넓힌다
    unknown = Extraction(product_code="NOPE", product_family="DRIVE")
    assert graph.candidates(unknown)[1] == "family"
    # 후보 안에 없는 에러코드는 무시한다 (오타·다른 제품군 코드)
    assert graph.candidates(EOC.model_copy(update={"error_code": "ZZ.9"}))[2] is None
    assert graph.candidates(Extraction()) == (None, None, None)  # 전체에서 찾는다


def test_search_returns_two_faults_with_path_representative_case_and_section(graph):
    results = graph.search(QUERY, EOC)

    assert [e.source for e in results] == ["cases", "cases"]
    top = results[0]
    assert top.metadata["pattern_id"] == "FLT-002"  # 증상(실행 즉시 · 케이블 절연)으로 가른다
    # 대표 사례는 같은 제품 사례, 문서 절은 그 사례가 인용한 절
    case = graph.store.nodes["Case"][top.doc_id]
    assert case["product_code"] == S100
    assert top.metadata["graph_path"] == (
        f"{S100} → E.OC → FLT-002 → {top.doc_id} → "
        f"{top.metadata['reference_doc_id']}#{top.metadata['reference_section']}"
    )
    assert top.metadata["reference_doc_id"] == f"TG-{S100}"
    assert all(e.metadata["error_code"] == "E.OC" for e in results)


def test_finalize_evidence_uses_graph_and_falls_back_to_patterns(graph):
    doc = Evidence(source="docs", doc_id="TG-X", section="3.1", text="t", score=0.5)
    pattern = Evidence(source="cases", doc_id="RC-OLD", text="old", metadata={"pattern_id": "P"})

    with_graph = finalize_evidence([doc, pattern], EOC, graph=graph, query=QUERY)
    assert with_graph[0] == doc
    assert [e.metadata.get("retriever") for e in with_graph[1:]] == ["graph", "graph"]

    class Broken:
        def search(self, *args, **kwargs):
            raise ConnectionError("neo4j down")

    assert finalize_evidence([doc, pattern], EOC, graph=Broken(), query=QUERY) == [doc, pattern]
    assert finalize_evidence([doc, pattern], EOC) == [doc, pattern]  # 그래프 꺼짐


def test_neo4j_cosine_score_is_rescaled_to_pgvector_scale():
    assert _cosine(1.0) == 1.0 and _cosine(0.5) == 0.0


def test_default_graph_is_off_unless_enabled_and_reachable(monkeypatch):
    assert knowledge_graph.default_graph(enabled=False) is None

    def refuse(settings=None):
        raise ConnectionError("no neo4j")

    monkeypatch.setattr(knowledge_graph, "connect", refuse)
    assert knowledge_graph.default_graph(enabled=True) is None  # 패턴 DB 로 돈다


# 학습 (CSA-72) -----------------------------------------------------------------------------------


def _case(ticket: str, cause: str, **extra) -> dict:
    return {
        "case_id": f"CASE-{ticket}",
        "ticket_id": ticket,
        "product_code": S100,
        "product_family": "DRIVE",
        "category": "DEFECT",
        "error_code": "E.OC",
        "summary": "Inverter trips at run",
        "cause": cause,
        "action": "Replaced the cable",
        "final_reply": "We replaced the damaged motor cable.",
        "cited": [f"TG-{S100}#3.2"],
        "active": True,
        **extra,
    }


def test_resolved_catalog_case_becomes_representative_until_reopened(graph):
    case = _case("T-1", "Motor cable insulation breakdown (phase-to-phase short)")
    case["pattern_id"] = "FLT-002"
    before = graph.store.case_count("FLT-002")

    graph.learn(case)
    top = graph.search(QUERY, EOC)[0]
    assert (top.metadata["pattern_id"], top.doc_id) == ("FLT-002", "CASE-T-1")  # 운영 사례 먼저
    assert graph.store.case_count("FLT-002") == before + 1

    graph.deactivate("T-1")  # 재문의로 다시 열림 → 대표 사례 · 해결 건수에서 빠진다
    top = graph.search(QUERY, EOC)[0]
    assert top.doc_id != "CASE-T-1"
    assert graph.store.case_count("FLT-002") == before


def test_new_cause_creates_live_fault_with_embedding(graph):
    cause = "Loose DC bus bar bolt causing arcing at run command"
    graph.learn(_case("T-2", cause))

    live = [f for f in graph.store.nodes["Fault"] if f.startswith("LIVE-DRIVE-")]
    assert len(live) == 1 and graph.store.has_vector(live[0])
    assert ("CASE-T-2", live[0]) in graph.store.rels["INSTANCE_OF"]
    assert (live[0], S100) in graph.store.rels["APPLIES_TO"]
    assert (live[0], f"TG-{S100}#3.2") in graph.store.rels["EXPLAINED_IN"]

    found = graph.search(f"{cause}. Inverter trips at run.", EOC)
    assert found[0].metadata["pattern_id"] == live[0]


def test_graph_learning_records_write_db_first_and_survive_graph_failure():
    class Records:
        def __init__(self):
            self.saved, self.closed = [], []

        def save_case(self, case):
            self.saved.append(case["case_id"])

        def deactivate_case(self, ticket_id):
            self.closed.append(ticket_id)

        def live_cases(self):
            return self.saved

    class Broken:
        def learn(self, case):
            raise ConnectionError("down")

        deactivate = learn

    records = Records()
    assert with_graph_learning(records, None) is records
    wrapped = with_graph_learning(records, Broken())
    assert isinstance(wrapped, GraphLearningRecords)
    wrapped.save_case({"case_id": "C-1"})
    wrapped.deactivate_case("T-1")
    assert (records.saved, records.closed, wrapped.live_cases()) == (["C-1"], ["T-1"], ["C-1"])


# 처리 흐름 (그래프 켬/끔) -----------------------------------------------------------------------

INQUIRY = {
    "channel": "email",
    "customer_tier": "GOLD",
    "language": "en",
    "subject": f"{S100} trips at run",
    "body": f"Our {S100} trips with over-current immediately at run command. "
    "Motor cable insulation may be damaged.",
    "category": "DEFECT",
    "provided_fields": {"serial_no": "X1", "fw_version": "1.0", "error_code": "E.OC"},
}


def _client(graph):
    return TestClient(
        create_app(
            llm=LLMRouter(Settings(_env_file=None)),
            agents=ANALYSIS,
            storage="memory",
            retrievers=(None, None),
            graph=graph,
        )
    )


@pytest.mark.parametrize("on", [True, False])
def test_same_inquiry_runs_end_to_end_with_graph_on_and_off(on):
    graph = KnowledgeGraph(memory_graph(), embed_fn=toy_embed) if on else None
    with _client(graph) as client:
        ticket = client.post("/api/tickets", json=INQUIRY).json()
        tid = ticket["ticket_id"]
        cases = [e for e in ticket["evidence"] if e["source"] == "cases"]
        if on:
            assert cases and all(e["metadata"]["graph_path"].startswith(S100) for e in cases)
        else:
            assert cases == []  # 사례 검색기 없음 (retrievers=(None, None))

        assert ticket["status"] == "READY_FOR_REVIEW"
        client.post(f"/api/tickets/{tid}/action", json={"action": "approve"})
        assert client.post(f"/api/tickets/{tid}/resolve").status_code == 200
        if on:  # 해결 확정 사례가 그래프에 학습된다
            assert graph.store.nodes["Case"][f"CASE-{tid}"]["active"] is True


def test_case_retrieval_table_lists_graph_next_to_current_methods():
    from cs_agent.evaluation.case_retrieval import table

    counts = {"n": 128, "pattern@1": 90, "pattern@2": 109, "graph@1": 92, "graph@2": 110}
    text = table({"split": "valid", "gold": counts, "rule": counts})
    assert "| 패턴 설명 임베딩 + 거름 (지금) | 90 | 109 | 90 | 109 |" in text
    assert "| 지식 그래프 (CSA-73) | 92 | 110 | 92 | 110 |" in text
    assert "지난 문의" not in text  # 재지 않은 방식은 빼고 그린다
