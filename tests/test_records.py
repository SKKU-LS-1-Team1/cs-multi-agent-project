from cs_agent.schemas import Extraction, InquiryIn
from cs_agent.services.records import MemoryRecords, ticket_row


def test_ticket_row_keeps_form_values_separate_from_confirmed_extraction():
    inquiry = InquiryIn(
        channel="email", body="Correct quantity to 10.", provided_fields={"quantity": "5"}
    )
    extraction = Extraction(provided_info=["quantity"], field_values={"quantity": "10"})
    row = ticket_row({"inquiry": inquiry, "extraction": extraction})
    assert row["provided_fields"] == {"quantity": "5"}
    assert row["field_values"] == {"quantity": "10"}
    row["field_values"]["quantity"] = "20"
    assert extraction.field_values == {"quantity": "10"}
    assert ticket_row({"inquiry": inquiry})["field_values"] == {}


def test_records_clear_withdrawn_values_instead_of_merging_old_values():
    records = MemoryRecords()
    inquiry = InquiryIn(channel="email", body="S100")
    records.add_ticket("T-1", inquiry)
    records.save_state(
        "T-1", {"inquiry": inquiry, "extraction": Extraction(field_values={"quantity": "10"})}
    )
    assert records.tickets["T-1"]["field_values"] == {"quantity": "10"}
    records.save_state("T-1", {"inquiry": inquiry, "extraction": Extraction()})
    assert records.tickets["T-1"]["field_values"] == {}
