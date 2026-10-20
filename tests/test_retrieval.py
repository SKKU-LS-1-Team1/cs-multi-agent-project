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
    keyword_cases,
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


def test_keyword_cases_exclude_non_train_tickets() -> None:
    cases = keyword_cases()
    case_ids = {e.doc_id for e, _ in cases.items}
    tickets = {e.metadata["ticket_id"] for e, _ in cases.items}

    path = get_settings().raw_data_dir / "tickets.csv"
    with path.open(encoding="utf-8-sig", newline="") as f:
        split = {r["ticket_id"]: r["data_split"] for r in csv.DictReader(f)}
    assert case_ids and {split[t] for t in tickets} == {"train"}


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
