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
