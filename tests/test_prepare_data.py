import pytest

pd = pytest.importorskip("pandas")

from cs_agent.pipeline.prepare_data import prepare_datasets  # noqa: E402


def _ticket(ticket_id: str, split: str, language: str = " EN ") -> dict[str, str]:
    return {
        "ticket_id": ticket_id,
        "data_split": split,
        "language": language,
        "body_language": "es",
        "contact_email_masked": "customer@***.masked",
        "inquiry_subject": f"Subject {ticket_id}",
        "inquiry_body": f"Body {ticket_id}",
        "category_code": " DEFECT ",
        "resolved_at_utc": "2025-10-02T09:17:23Z",
    }


def test_prepare_datasets_keeps_splits_and_excludes_holdout_cases() -> None:
    train_ticket = _ticket("T-1", "train")
    tickets = pd.DataFrame(
        [
            train_ticket,
            train_ticket.copy(),
            _ticket("T-2", "train", "FR"),
            _ticket("V-1", "valid"),
            _ticket("X-1", "test"),
        ]
    )
    cases = pd.DataFrame(
        [
            {"case_id": "C-1", "ticket_id": "T-1"},
            {"case_id": "C-2", "ticket_id": "T-2"},
            {"case_id": "C-3", "ticket_id": "V-1"},
            {"case_id": "C-4", "ticket_id": "X-1"},
        ]
    )

    prepared = prepare_datasets(tickets, cases)

    assert len(prepared.tickets_by_split["train"]) == 2
    assert len(prepared.tickets_by_split["valid"]) == 1
    assert len(prepared.tickets_by_split["test"]) == 1
    assert prepared.ticket_duplicates_removed == 1
    assert set(prepared.cases_seed["ticket_id"]) == {"T-1", "T-2"}
    assert prepared.cases_excluded == 2
    assert prepared.classifier_train.columns.tolist() == ["text", "category_code"]
    assert prepared.classifier_train.iloc[0].to_dict() == {
        "text": "Subject T-1\nBody T-1",
        "category_code": "DEFECT",
    }
    assert set(prepared.tickets_by_split["train"]["language"]) == {"en", "fr"}
    assert set(prepared.tickets_by_split["train"]["body_language"]) == {"es"}
    assert prepared.language_mismatch_count == 4


def test_prepare_datasets_rejects_unmasked_contact_email() -> None:
    tickets = pd.DataFrame([_ticket("T-1", "train")])
    tickets.loc[0, "contact_email_masked"] = "customer@example.com"
    cases = pd.DataFrame([{"case_id": "C-1", "ticket_id": "T-1"}])

    with pytest.raises(ValueError, match="without a mask marker"):
        prepare_datasets(tickets, cases)


def test_prepare_datasets_cleans_holdout_labels_and_codes() -> None:
    valid = _ticket("V-1", "valid", "zh-CN")
    valid["body_language"] = "klingon"
    tickets = pd.DataFrame([_ticket("T-1", " Train "), valid])
    cases = pd.DataFrame([{"case_id": "C-1", "ticket_id": "T-1"}])

    prepared = prepare_datasets(tickets, cases)

    valid_row = prepared.tickets_by_split["valid"].iloc[0]
    assert valid_row["category_code"] == "DEFECT"
    assert valid_row["language"] == "zh"
    assert pd.isna(valid_row["body_language"])
    assert prepared.invalid_language_count == 1
    assert len(prepared.tickets_by_split["train"]) == 1


def test_prepare_datasets_drops_train_text_seen_in_holdout() -> None:
    leaked = _ticket("T-1", "train")
    holdout = _ticket("X-1", "test")
    holdout["inquiry_subject"] = "  subject t-1 "
    holdout["inquiry_body"] = "Body   T-1"
    tickets = pd.DataFrame([leaked, _ticket("T-2", "train"), holdout])
    cases = pd.DataFrame(
        [
            {"case_id": "C-1", "ticket_id": "T-1"},
            {"case_id": "C-2", "ticket_id": "T-2"},
        ]
    )

    prepared = prepare_datasets(tickets, cases)

    assert prepared.train_text_leaks_removed == 1
    assert prepared.tickets_by_split["train"]["ticket_id"].tolist() == ["T-2"]
    assert prepared.tickets_by_split["test"]["ticket_id"].tolist() == ["X-1"]
    assert prepared.cases_seed["case_id"].tolist() == ["C-2"]
    assert prepared.cases_excluded == 1
    assert prepared.classifier_train["text"].tolist() == ["Subject T-2\nBody T-2"]


def test_prepare_datasets_keeps_text_columns_and_counts_body_contacts() -> None:
    ticket = _ticket("T-1", "train")
    ticket["fw_version_reported"] = "3.10"
    ticket["sla_resolution_target_h"] = "240"
    ticket["inquiry_body"] = "IEC 62443-4-2 on 2025-11-16. Call me at +49 30 1234 5678"
    tickets = pd.DataFrame([ticket])
    cases = pd.DataFrame([{"case_id": "C-1", "ticket_id": "T-1"}])

    prepared = prepare_datasets(tickets, cases)

    train_row = prepared.tickets_by_split["train"].iloc[0]
    assert train_row["fw_version_reported"] == "3.10"
    assert train_row["sla_resolution_target_h"] == 240
    assert prepared.body_contact_count == 1
