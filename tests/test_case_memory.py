from cs_agent.agents.case_memory import SAVE_ON, build_case, mask_pii
from cs_agent.domain import Category, FeedbackReason, ReviewAction
from cs_agent.schemas import Classification, Draft, Extraction, InquiryIn, ReviewIn


def test_save_on():
    assert {ReviewAction.APPROVE, ReviewAction.EDIT_APPROVE, ReviewAction.ESCALATE} == SAVE_ON
    for action in (ReviewAction.REWRITE, ReviewAction.INFO_REQUEST, ReviewAction.REJECT):
        assert action not in SAVE_ON


def test_mask_pii():
    text = (
        "Mail user1@acme.com, Tel: 02-1234-5678, +82 10 1234 5678, COMPANY_2464_0436, "
        "Serial number (nameplate): AB12345, S/N: XG-99812. Commissioning 2025-11-16."
    )
    masked = mask_pii(text)
    for secret in ("user1@acme.com", "1234", "COMPANY_2464_0436", "AB12345", "XG-99812"):
        assert secret not in masked
    assert "2025-11-16" in masked


def test_build_case_uses_edited_reply():
    state = {
        "ticket_id": "T-1",
        "inquiry": InquiryIn(channel="EMAIL", subject="PLC P.06 fault", body="..."),
        "classification": Classification(category=Category.DEFECT),
        "extraction": Extraction(product_code="PLC-XGB-XBM-DR16S", product_family="PLC"),
        "draft": Draft(text="AI draft", slots={"cause": "PSU degraded"}, cited=["TG-PLC#3.8"]),
        "review": ReviewIn(
            action=ReviewAction.EDIT_APPROVE,
            edited_text="Fixed reply to user1@acme.com",
            feedback_reason=FeedbackReason.FACT_ERROR,
        ),
        "final_reply": "Fixed reply to user1@acme.com",
    }
    case = build_case(state)
    assert case["case_id"] == "CASE-T-1"
    assert case["final_reply"] == "Fixed reply to **MASKED**"
    assert case["edited"] and case["source_fix_needed"]
    assert case["category"] == "DEFECT"
    assert "Cause: PSU degraded" in case["text"]


# --- 피드백 루프: 운영 중 해결 사례를 다음 검색에 (CSA-15) -------------------------------------


def _live_case(case_id: str, summary: str, **values) -> dict:
    return {
        "case_id": case_id,
        "ticket_id": case_id.removeprefix("CASE-"),
        "text": summary,
        "summary": summary,
        "product_code": "TRF-OIL-1000",
        "product_family": "OIL_TRF",
        "category": "TECH_SPEC",
        "error_code": None,
        "cause": "",
        "action": "",
        "final_reply": "Dimensions are in datasheet section 2.",
        "cited": ["DS-TRF-OIL-1000#2"],
        "active": True,
    } | values


class _Records:
    def __init__(self, cases):
        self.cases = cases

    def live_cases(self):
        return [c for c in self.cases if c.get("active", True)]


def test_case_evidence_matches_keyword_case_shape():
    from cs_agent.agents.case_memory import case_evidence

    evidence = case_evidence(_live_case("CASE-T-1", "Zebra dimensions question"))

    assert (evidence.source, evidence.doc_id) == ("cases", "CASE-T-1")
    assert evidence.text.startswith("Summary: Zebra dimensions question")
    assert "Final reply: Dimensions are in datasheet section 2." in evidence.text
    assert evidence.metadata == {
        "category": "TECH_SPEC",
        "product_code": "TRF-OIL-1000",
        "family": "OIL_TRF",
        "error_code": "",
        "ticket_id": "T-1",
        "reference_doc_id": "DS-TRF-OIL-1000",
    }


def test_live_cases_retriever_adds_resolved_cases_to_keyword_search():
    from cs_agent.agents.case_memory import LiveCasesRetriever, case_evidence
    from cs_agent.agents.retrieval import KeywordRetriever

    seed = case_evidence(
        _live_case("CASE-SEED", "Breaker trips at startup", final_reply="Reset the relay.")
    )
    base = KeywordRetriever([(seed, seed.text)])
    records = _Records(
        [_live_case("CASE-T-1", "Zebra transformer dimensions", final_reply="See sheet.")]
    )
    retriever = LiveCasesRetriever(base, records)

    assert [e.doc_id for e in retriever.search("zebra dimensions", 3)] == ["CASE-T-1"]
    assert [e.doc_id for e in retriever.search("breaker trips", 3)] == ["CASE-SEED"]
    # 다시 열린 문의(active=False)는 검색에서 빠진다
    records.cases[0]["active"] = False
    assert retriever.search("zebra dimensions", 3) == []
    # 같은 case_id 면 운영 사례가 이긴다 (seed 를 덮는다)
    records.cases = [_live_case("CASE-SEED", "Zebra breaker answer updated", final_reply="")]
    hits = retriever.search("breaker", 3)
    assert [h.doc_id for h in hits] == ["CASE-SEED"] and "updated" in hits[0].text


def test_with_live_cases_wraps_only_keyword_search():
    from cs_agent.agents.case_memory import LiveCasesRetriever, with_live_cases
    from cs_agent.agents.retrieval import KeywordRetriever

    records = _Records([])
    assert isinstance(with_live_cases(KeywordRetriever([]), records), LiveCasesRetriever)
    pgvector_like = object()
    assert with_live_cases(pgvector_like, records) is pgvector_like
    assert with_live_cases(None, records) is None


def test_resolved_ticket_becomes_evidence_for_next_inquiry():
    """루프 끝까지: 문의 A 를 승인·해결 → 비슷한 문의 B 의 근거 후보에 A 의 사례가 나온다."""
    from fastapi.testclient import TestClient
    from stubs import ANALYSIS

    from cs_agent.agents.retrieval import KeywordRetriever
    from cs_agent.config import Settings
    from cs_agent.llm.router import LLMRouter
    from cs_agent.main import create_app

    inquiry = {
        "channel": "email",
        "customer_tier": "GOLD",
        "language": "en",
        "subject": "Zebrawood enclosure dimensions of TRF-OIL-1000",
        "body": "What are the zebrawood enclosure dimensions and weight of TRF-OIL-1000?",
        "category": "TECH_SPEC",
        "provided_fields": {"application": "substation"},
    }
    with TestClient(
        create_app(
            llm=LLMRouter(Settings(_env_file=None)),
            agents=ANALYSIS,
            storage="memory",
            retrievers=(None, KeywordRetriever([])),  # 사례 seed 없음 → 운영 사례만
        )
    ) as client:
        first = client.post("/api/tickets", json=inquiry).json()
        assert not [e for e in first["evidence"] if e["source"] == "cases"]
        client.post(f"/api/tickets/{first['ticket_id']}/action", json={"action": "approve"})
        assert client.post(f"/api/tickets/{first['ticket_id']}/resolve").status_code == 200

        second = client.post("/api/tickets", json=inquiry).json()

    cases = [e["doc_id"] for e in second["evidence"] if e["source"] == "cases"]
    assert cases == [f"CASE-{first['ticket_id']}"]
