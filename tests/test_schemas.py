from cs_agent.config import get_settings
from cs_agent.domain import BUNDLE_OF, Category, ReviewAction
from cs_agent.graph.state import TicketState
from cs_agent.schemas import Extraction, InquiryIn, ReviewIn, TicketOut


def test_every_category_has_bundle():
    assert set(BUNDLE_OF) == set(Category)


def test_settings_paths_exist():
    settings = get_settings()
    assert (settings.ref_dir / "routing_rules.csv").exists()
    assert settings.max_verify_retries == 2


def test_review_round_trip():
    # 그래프 resume 값은 model_dump(mode="json") 로 넘어간다
    review = ReviewIn(action=ReviewAction.EDIT_APPROVE, edited_text="ok")
    assert ReviewIn.model_validate(review.model_dump(mode="json")) == review


def test_inquiry_defaults():
    inquiry = InquiryIn(channel="EMAIL", body="hello")
    assert inquiry.customer_tier == "STANDARD"
    assert inquiry.received_at.tzinfo is not None


def test_ticket_state_partial():
    state: TicketState = {"ticket_id": "T-1", "retries": 0}
    out = TicketOut(ticket_id=state["ticket_id"], status="NEW")
    assert out.checks == []


def test_old_extraction_payload_defaults_to_empty_field_values():
    old = Extraction.model_validate({"product_code": "TEST", "provided_info": ["quantity"]})
    assert old.field_values == {}
    populated = Extraction(field_values={"quantity": "10", "incoterms": "FOB"})
    assert Extraction.model_validate_json(populated.model_dump_json()) == populated
    assert old.field_values == {}
