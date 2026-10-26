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


E_OC_CAUSE = "Acceleration time too short for load inertia"  # fault_catalog FLT-001 의 원인


def test_resolved_cases_are_learned_as_patterns_and_found_by_pattern():
    """해결 사례는 패턴으로 묶여 배운다: 카탈로그 원인이면 그 고장 패턴, 새 원인이면 새 패턴."""
    from cs_agent.agents.case_patterns import MemoryPatternRetriever

    seed = _live_case(
        "RC-SEED",
        "Inverter trips at acceleration",
        product_code="INV-LSLV0075-S100",
        product_family="DRIVE",
        error_code="E.OC",
        cause=E_OC_CAUSE,
        data_split="train",
        final_reply="Increase ACC time.",
    )
    records = _Records(
        [_live_case("CASE-T-1", "Zebra transformer dimensions", cause="Datasheet question")]
    )
    retriever = MemoryPatternRetriever([seed], records)

    hit = retriever.search("zebra transformer dimensions", 3)
    assert [e.doc_id for e in hit] == ["CASE-T-1"]
    assert hit[0].metadata["pattern_id"].startswith("LIVE-OIL_TRF-")  # 카탈로그에 없는 원인
    hit = retriever.search("acceleration time load inertia", 3)
    assert [(e.doc_id, e.metadata["pattern_id"]) for e in hit] == [("RC-SEED", "FLT-001")]
    assert "Symptom: Over-current trip during acceleration" in hit[0].text  # 패턴 설명

    # 다시 열린 문의(active=False)는 패턴에서 빠진다
    records.cases[0]["active"] = False
    assert retriever.search("zebra transformer dimensions", 3) == []

    # 같은 고장으로 운영 중 해결되면 같은 패턴에 쌓이고, 운영 사례가 대표가 된다
    records.cases = [
        _live_case(
            "CASE-T-2",
            "S100 trips E.OC",
            product_family="DRIVE",
            cause=E_OC_CAUSE,
            final_reply="Raised ACC time to 12 s, fixed.",
        )
    ]
    hit = retriever.search("acceleration time load inertia", 3)
    assert [(e.doc_id, e.metadata["pattern_id"]) for e in hit] == [("CASE-T-2", "FLT-001")]
    assert hit[0].metadata["case_count"] == "2"
    assert "Resolved 2 time(s), 1 in operation" in hit[0].text
    assert "Raised ACC time to 12 s" in hit[0].text


def test_with_live_cases_attaches_records_to_local_pattern_search():
    from cs_agent.agents.case_memory import with_live_cases
    from cs_agent.agents.case_patterns import MemoryPatternRetriever

    records = _Records([])
    local = MemoryPatternRetriever([])
    assert with_live_cases(local, records) is local and local.records is records
    pgvector_like = object()
    assert with_live_cases(pgvector_like, records) is pgvector_like
    assert with_live_cases(None, records) is None


def test_resolved_ticket_becomes_evidence_for_next_inquiry():
    """루프 끝까지: 문의 A 를 승인·해결 → 비슷한 문의 B 의 근거 후보에 A 의 사례가 나온다."""
    from fastapi.testclient import TestClient
    from stubs import ANALYSIS

    from cs_agent.agents.case_patterns import MemoryPatternRetriever
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
            retrievers=(None, MemoryPatternRetriever([])),  # 사례 seed 없음 → 운영 사례만
        )
    ) as client:
        first = client.post("/api/tickets", json=inquiry).json()
        assert not [e for e in first["evidence"] if e["source"] == "cases"]
        client.post(f"/api/tickets/{first['ticket_id']}/action", json={"action": "approve"})
        assert client.post(f"/api/tickets/{first['ticket_id']}/resolve").status_code == 200

        second = client.post("/api/tickets", json=inquiry).json()

    cases = [e["doc_id"] for e in second["evidence"] if e["source"] == "cases"]
    assert cases == [f"CASE-{first['ticket_id']}"]
