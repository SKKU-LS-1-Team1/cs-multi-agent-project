import csv
from types import SimpleNamespace

import pytest

from cs_agent.agents.retrieval import (
    KeywordRetriever,
    PgVectorRetriever,
    finalize_evidence,
    find_error_codes,
    first_pass,
    k3_hit,
    keyword_docs,
    measure_k3,
)
from cs_agent.config import get_settings
from cs_agent.domain import Category
from cs_agent.schemas import Evidence, Extraction


def _chunk(doc_id: str, section: str, title: str, text: str, product: str, family: str):
    # pipeline/chunking.Chunk 와 같은 모양 (CSA-18)
    doc_type = doc_id.split("-")[0]
    metadata = {"title": doc_id, "doc_type": doc_type, "product_code": product, "family": family}
    return SimpleNamespace(
        doc_id=doc_id, section=section, title=title, text=text, metadata=metadata
    )


CHUNKS = [
    _chunk("DS-INV-A", "2.1", "Ratings", "Rated output 7.5 kW, input 380 V", "INV-A", "DRIVE"),
    _chunk(
        "TG-INV-A",
        "3.1",
        "E.OC — Over-current trip",
        "Increase acceleration time",
        "INV-A",
        "DRIVE",
    ),
    _chunk(
        "TG-INV-A",
        "3.4",
        "E.OV — Over-voltage trip",
        "Increase deceleration time",
        "INV-A",
        "DRIVE",
    ),
    _chunk("DS-PLC-B", "2.1", "Ratings", "Rated output 24 V DC input", "PLC-B", "PLC"),
    _chunk("POL-WARRANTY", "1", "Warranty period", "Warranty is 24 months from delivery", "", ""),
]


def _doc(doc_id: str, section: str, score: float, **metadata: str) -> Evidence:
    return Evidence(
        source="docs", doc_id=doc_id, section=section, text="t", score=score, metadata=metadata
    )


def test_keyword_retriever_scores_and_filters() -> None:
    docs = keyword_docs(CHUNKS)

    hits = docs.search("rated output of the drive", k=2)
    assert [h.doc_id for h in hits][:2] == ["DS-INV-A", "DS-PLC-B"]
    assert hits[0].score > 0 and hits[0].metadata["doc_type"] == "DS"

    only_plc = docs.search("rated output", k=5, where={"product_code": "PLC-B"})
    assert [h.doc_id for h in only_plc] == ["DS-PLC-B"]
    assert docs.search("완전히 다른 언어", k=5) == []


def test_local_case_patterns_learn_only_train_tickets() -> None:
    from cs_agent.agents.case_patterns import train_cases

    cases = train_cases()
    path = get_settings().raw_data_dir / "resolution_cases.csv"
    with path.open(encoding="utf-8-sig", newline="") as f:
        ticket_of = {r["case_id"]: r["ticket_id"] for r in csv.DictReader(f)}
    path = get_settings().raw_data_dir / "tickets.csv"
    with path.open(encoding="utf-8-sig", newline="") as f:
        split = {r["ticket_id"]: r["data_split"] for r in csv.DictReader(f)}
    assert cases and {split[ticket_of[c["case_id"]]] for c in cases} == {"train"}


def test_find_error_codes_matches_whole_code() -> None:
    codes = {"E.OC", "E.OV", "P.06"}

    assert find_error_codes("Drive shows E.OC on start.", codes) == ["E.OC"]
    assert find_error_codes("code XE.OCX and P.061", codes) == []


def test_first_pass_merges_docs_cases_and_error_code_search() -> None:
    docs = keyword_docs(CHUNKS)
    cases = KeywordRetriever(
        [(Evidence(source="cases", doc_id="RC-1", text="c"), "inverter trips during acceleration")]
    )

    result = first_pass(docs, cases, "Inverter trips with E.OC during acceleration")

    assert {e.source for e in result} == {"docs", "cases"}
    assert ("TG-INV-A", "3.1") in {(e.doc_id, e.section) for e in result}
    assert len({(e.doc_id, e.section, e.text) for e in result}) == len(result)
    assert first_pass(None, None, "anything") == []


def test_finalize_filters_other_products_and_boosts_category_and_error_code() -> None:
    candidates = [
        _doc("DS-PLC-B", "2.1", 0.9, doc_type="DS", product_code="PLC-B", family="PLC"),
        _doc("DS-INV-A", "2.1", 0.6, doc_type="DS", product_code="INV-A", family="DRIVE"),
        _doc(
            "TG-INV-A",
            "3.4",
            0.5,
            doc_type="TG",
            product_code="INV-A",
            family="DRIVE",
            title="3.4. E.OV — Over-voltage",
        ),
        _doc(
            "TG-INV-A",
            "3.1",
            0.2,
            doc_type="TG",
            product_code="INV-A",
            family="DRIVE",
            title="3.1. E.OC — Over-current",
        ),
        _doc("POL-WARRANTY", "1", 0.4, doc_type="POL"),
        Evidence(
            source="cases",
            doc_id="RC-1",
            text="c",
            score=0.9,
            metadata={"category": "TECH_SPEC", "product_code": "INV-A"},
        ),
        Evidence(
            source="cases",
            doc_id="RC-2",
            text="c",
            score=0.5,
            metadata={"category": "DEFECT", "product_code": "INV-A"},
        ),
    ]
    extraction = Extraction(product_code="INV-A", product_family="DRIVE", error_code="E.OC")

    result = finalize_evidence(candidates, extraction, k=3, category=Category.DEFECT)

    docs = [(e.doc_id, e.section) for e in result if e.source == "docs"]
    assert docs == [("TG-INV-A", "3.1"), ("TG-INV-A", "3.4"), ("DS-INV-A", "2.1")]
    assert [e.doc_id for e in result if e.source == "cases"] == ["RC-2", "RC-1"]

    warranty = finalize_evidence(candidates, extraction, k=1, category=Category.WARRANTY)
    assert warranty[0].doc_id == "POL-WARRANTY"


def test_finalize_keeps_one_piece_per_section() -> None:
    candidates = [_doc("DS-INV-A", "2.1", 0.5), _doc("DS-INV-A", "2.1", 0.7)]

    result = finalize_evidence(candidates, Extraction(), k=3)

    assert [(e.doc_id, e.score) for e in result] == [("DS-INV-A", 0.7)]


def test_k3_hit_and_measure() -> None:
    evidence = [_doc("TG-INV-A", "3.1", 1.0)]
    assert k3_hit(evidence, "TG-INV-A", "3.1")
    assert k3_hit(evidence, "TG-INV-A", "")
    assert not k3_hit(evidence, "TG-INV-A", "3.4")

    row = {
        "reference_doc_id": "TG-INV-A",
        "reference_section": "3.1",
        "inquiry_subject": "E.OC trip",
        "inquiry_body": "Over-current trip when accelerating",
        "product_code": "INV-A",
        "product_family": "DRIVE",
        "error_code_reported": "E.OC",
        "category_code": "DEFECT",
    }
    result = measure_k3([row], keyword_docs(CHUNKS), KeywordRetriever([]))
    assert (result["hits"], result["total"]) == (1, 1)


def test_pgvector_retriever_rejects_unknown_filter() -> None:
    retriever = PgVectorRetriever("doc_chunks", engine=object(), embed_fn=lambda q: [0.0])

    with pytest.raises(ValueError, match="거를 수 없는"):
        retriever.search("q", where={"text; DROP TABLE": "x"})
    with pytest.raises(ValueError):
        PgVectorRetriever("tickets")


def test_pgvector_case_row_maps_db_columns() -> None:
    """resolution_cases 열 이름(db/models.py)대로 읽어 키워드 사례와 같은 모양으로 만든다."""
    retriever = PgVectorRetriever("resolution_cases", engine=object(), embed_fn=lambda q: [0.0])
    row = {
        "case_id": "CASE-1",
        "ticket_id": "T-1",
        "category": "DEFECT",
        "product_code": "INV-A",
        "product_family": "DRIVE",
        "error_code": "E.OC",
        "summary": "Trip on start",
        "cause": "Accel time too short",
        "action": "Increase accel time",
        "final_reply": "Please increase the accel time.",
        "cited": ["TG-INV-A#3.1"],
        "distance": 0.25,
    }

    evidence = retriever._evidence(row)

    assert (evidence.source, evidence.doc_id, evidence.score) == ("cases", "CASE-1", 0.75)
    assert "Action: Increase accel time" in evidence.text
    assert evidence.metadata["family"] == "DRIVE"
    assert evidence.metadata["reference_doc_id"] == "TG-INV-A"
    assert retriever._evidence({**row, "cited": []}).metadata["reference_doc_id"] == ""


# reranker (CSA-81) ---------------------------------------------------------------------------


class _RerankLLM:
    """절 id 별 관련도를 정해 둔 판단 대역. model 을 'fake' 로 주면 LLM 꺼짐."""

    def __init__(self, yes: dict[str, float], *, enabled=True, model="jev", fail=False):
        self.settings = SimpleNamespace(rerank_enabled=enabled, rerank_weight=0.5)
        self.yes, self.model, self.fail = yes, model, fail
        self.calls: list[str] = []

    def judge(self, task, prompt, options):
        from cs_agent.llm.clients import Judgement

        if self.fail:
            raise RuntimeError("timeout")
        self.calls.append(task)
        doc = next(d for d in self.yes if f"Section: {d} " in prompt)
        p = self.yes[doc]
        return Judgement("yes" if p >= 0.5 else "no", p if p >= 0.5 else 1 - p, self.model)


RERANK_CANDIDATES = [
    _doc("DS-INV-A", "2.1", 0.80, doc_type="DS", product_code="INV-A", family="DRIVE"),
    _doc("DS-INV-A", "4.2", 0.75, doc_type="DS", product_code="INV-A", family="DRIVE"),
    _doc("DS-INV-A", "5.1", 0.70, doc_type="DS", product_code="INV-A", family="DRIVE"),
    _doc("DS-INV-A", "6.3", 0.60, doc_type="DS", product_code="INV-A", family="DRIVE"),
]
RERANK_YES = {"DS-INV-A 2.1": 0.1, "DS-INV-A 4.2": 0.2, "DS-INV-A 5.1": 0.3, "DS-INV-A 6.3": 0.95}
EXTRACTION = Extraction(product_code="INV-A", product_family="DRIVE")


def _sections(result):
    return [e.section for e in result if e.source == "docs"]


def test_rerank_lifts_relevant_section_into_top3() -> None:
    llm = _RerankLLM(RERANK_YES)

    before = finalize_evidence(RERANK_CANDIDATES, EXTRACTION, k=3, query="IP rating?")
    after = finalize_evidence(RERANK_CANDIDATES, EXTRACTION, k=3, query="IP rating?", llm=llm)

    assert _sections(before) == ["2.1", "4.2", "5.1"]
    assert _sections(after)[0] == "6.3"
    assert after[0].metadata["rerank"] == "0.950"
    assert llm.calls == ["rerank"] * 4


def test_rerank_keeps_exact_error_code_section_on_top() -> None:
    title = "3.1. E.OC — Over-current"
    candidates = [
        *RERANK_CANDIDATES,
        _doc("TG-INV-A", "3.1", 0.2, doc_type="TG", product_code="INV-A", title=title),
    ]
    yes = {**RERANK_YES, "TG-INV-A 3.1": 0.0}
    extraction = Extraction(product_code="INV-A", error_code="E.OC")

    result = finalize_evidence(
        candidates, extraction, k=3, category=Category.DEFECT, query="E.OC", llm=_RerankLLM(yes)
    )

    assert [(e.doc_id, e.section) for e in result][:2] == [("TG-INV-A", "3.1"), ("DS-INV-A", "6.3")]


@pytest.mark.parametrize(
    "llm",
    [
        None,
        _RerankLLM(RERANK_YES, enabled=False),
        _RerankLLM(RERANK_YES, model="fake"),
        _RerankLLM(RERANK_YES, fail=True),
    ],
    ids=["no-router", "disabled", "llm-off", "judge-fails"],
)
def test_rerank_falls_back_to_rule_order(llm) -> None:
    result = finalize_evidence(RERANK_CANDIDATES, EXTRACTION, k=3, query="IP rating?", llm=llm)

    assert _sections(result) == ["2.1", "4.2", "5.1"]


def test_measure_rerank_compares_off_and_on() -> None:
    from cs_agent.agents.retrieval import measure_rerank

    row = {
        "reference_doc_id": "DS-INV-A",
        "reference_section": "6.3",
        "inquiry_subject": "IP rating",
        "inquiry_body": "What is the enclosure rating?",
        "product_code": "INV-A",
        "product_family": "DRIVE",
        "error_code_reported": "",
        "category_code": "TECH_SPEC",
    }

    class Fixed:
        def search(self, query, k, where=None):
            return list(RERANK_CANDIDATES)

    result = measure_rerank([row], Fixed(), None, _RerankLLM(RERANK_YES), weights=(0.5,))

    assert (result["base"], result["pool"], result["rerank"][0.5]) == (0, 1, 1)


# 하이브리드 (멘토링 개선안 4) --------------------------------------------------------------------


class _VectorDocs:
    """pgvector docs 대역: search 는 정해 둔 순서, score_sections 는 정해 둔 벡터 점수."""

    calibrated = True

    def __init__(self, ranked: list[Evidence], scores: dict[tuple[str, str], float]):
        self.ranked, self.scores = ranked, scores
        self.asked: list[tuple[str, str]] = []

    def search(self, query, k=5, where=None):
        found = [
            e
            for e in self.ranked
            if not where or all(e.metadata.get(c) == v for c, v in where.items())
        ]
        return found[:k]

    def score_sections(self, query, keys):
        self.asked.extend(keys)
        return [
            _doc(doc_id, section, self.scores[(doc_id, section)], doc_type=doc_id.split("-")[0])
            for doc_id, section in keys
            if (doc_id, section) in self.scores
        ]


def _hybrid_settings(monkeypatch, enabled: bool, weight: float = 0.3) -> None:
    from cs_agent.agents import retrieval

    settings = SimpleNamespace(hybrid_enabled=enabled, hybrid_weight=weight)
    monkeypatch.setattr(retrieval, "get_settings", lambda: settings)
    monkeypatch.setattr(retrieval, "_keyword_index", lambda: keyword_docs(CHUNKS))


def test_first_pass_hybrid_adds_keyword_sections(monkeypatch) -> None:
    _hybrid_settings(monkeypatch, enabled=True)
    vector = _VectorDocs([_doc("DS-INV-A", "2.1", 0.8, doc_type="DS")], {("TG-INV-A", "3.4"): 0.6})
    found = first_pass(vector, None, "deceleration time keeps tripping")
    by_key = {(e.doc_id, e.section): e for e in found}
    # 벡터 top 밖이던 TG 3.4 가 키워드로 들어오고, 벡터 점수 + 키워드 점수 × 0.3
    assert ("TG-INV-A", "3.4") in vector.asked
    assert by_key[("TG-INV-A", "3.4")].score > 0.6
    assert by_key[("TG-INV-A", "3.4")].metadata["keyword"]
    assert by_key[("DS-INV-A", "2.1")].score == 0.8  # 키워드에 안 걸린 근거는 그대로


def test_first_pass_hybrid_off_is_vector_only(monkeypatch) -> None:
    _hybrid_settings(monkeypatch, enabled=False)
    vector = _VectorDocs([_doc("DS-INV-A", "2.1", 0.8, doc_type="DS")], {("TG-INV-A", "3.4"): 0.6})
    found = first_pass(vector, None, "deceleration time keeps tripping")
    assert [(e.doc_id, e.section) for e in found] == [("DS-INV-A", "2.1")]
    assert vector.asked == []


def test_first_pass_hybrid_skips_keyword_retriever(monkeypatch) -> None:
    # 로컬 대체 구현(키워드 검색)이면 섞을 벡터가 없으니 그대로
    _hybrid_settings(monkeypatch, enabled=True)
    found = first_pass(keyword_docs(CHUNKS), None, "deceleration time")
    assert all("keyword" not in e.metadata for e in found)


def test_measure_hybrid_counts_off_and_on(monkeypatch) -> None:
    from cs_agent.agents.retrieval import measure_hybrid

    _hybrid_settings(monkeypatch, enabled=False)
    vector = _VectorDocs(
        [
            _doc("DS-INV-A", "2.1", 0.9, doc_type="DS", product_code="INV-A"),
            _doc("TG-INV-A", "3.1", 0.85, doc_type="TG", product_code="INV-A"),
            _doc("DS-PLC-B", "2.1", 0.8, doc_type="DS", product_code="PLC-B"),
        ],
        {("TG-INV-A", "3.4"): 0.5},
    )
    row = {
        "ticket_id": "T-1",
        "inquiry_subject": "Over-voltage",
        "inquiry_body": "deceleration time",
        "product_code": "",
        "product_family": "",
        "error_code_reported": "",
        "category_code": "MANUAL",
        "language": "en",
        "reference_doc_id": "TG-INV-A",
        "reference_section": "3.4",
    }
    result = measure_hybrid([row], vector, weights=(1.0,), keyword=keyword_docs(CHUNKS))
    assert result["total"] == 1
    assert result["base"] == {"k3": 0, "pool": 0}
    assert result["hybrid"][1.0] == {"k3": 1, "pool": 1}
    assert result["by_group"]["language"]["en"] == {"n": 1, "off": 0, "1.0": 1}
