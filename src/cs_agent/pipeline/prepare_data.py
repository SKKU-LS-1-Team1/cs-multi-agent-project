# 상담 이력 정제, 학습·시험 분리 (CSA-17 · 담당 박종석 · Sprint 1)
# 실행 예: uv run --extra data python -m cs_agent.pipeline.prepare_data
#
# 입력: data/raw/cs_tickets_resolution_v1.xlsx
# 출력: data/processed/ 의 tickets_train/valid/test, cases_seed,
#       classifier_train parquet

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[3]
INPUT_PATH = PROJECT_ROOT / "data" / "raw" / "cs_tickets_resolution_v1.xlsx"
OUTPUT_DIR = PROJECT_ROOT / "data" / "processed"

TICKET_COLUMNS = {
    "ticket_id",
    "data_split",
    "language",
    "body_language",
    "contact_email_masked",
    "inquiry_subject",
    "inquiry_body",
    "category_code",
    "resolved_at_utc",
}
CASE_COLUMNS = {"case_id", "ticket_id"}
SPLITS = ("train", "valid", "test")


@dataclass(frozen=True)
class PreparedDatasets:
    tickets_by_split: dict[str, pd.DataFrame]
    cases_seed: pd.DataFrame
    classifier_train: pd.DataFrame
    ticket_duplicates_removed: int
    case_duplicates_removed: int
    holdout_cases_removed: int
    masked_email_count: int
    email_value_count: int
    language_mismatch_count: int


def _require_columns(frame: pd.DataFrame, required: set[str], name: str) -> None:
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"{name} sheet is missing required columns: {', '.join(missing)}")


def _deduplicate(frame: pd.DataFrame, key: str, name: str) -> tuple[pd.DataFrame, int]:
    original_count = len(frame)
    cleaned = frame.drop_duplicates().copy()
    removed_count = original_count - len(cleaned)

    cleaned[key] = cleaned[key].astype("string").str.strip()
    missing_ids = cleaned[key].isna() | cleaned[key].eq("")
    if missing_ids.any():
        raise ValueError(f"{name} contains {int(missing_ids.sum())} rows without {key}")

    duplicate_ids = cleaned[key].duplicated(keep=False)
    if duplicate_ids.any():
        duplicate_count = int(cleaned.loc[duplicate_ids, key].nunique())
        raise ValueError(f"{name} contains {duplicate_count} conflicting duplicate {key} values")

    return cleaned.reset_index(drop=True), removed_count


def prepare_datasets(tickets: pd.DataFrame, cases: pd.DataFrame) -> PreparedDatasets:
    _require_columns(tickets, TICKET_COLUMNS, "tickets")
    _require_columns(cases, CASE_COLUMNS, "resolution_cases")

    tickets, ticket_duplicates_removed = _deduplicate(tickets, "ticket_id", "tickets")
    cases, case_duplicates_removed = _deduplicate(cases, "case_id", "resolution_cases")
    cases["ticket_id"] = cases["ticket_id"].astype("string").str.strip()

    invalid_splits = tickets["data_split"].isna() | ~tickets["data_split"].isin(SPLITS)
    if invalid_splits.any():
        values = sorted(tickets.loc[invalid_splits, "data_split"].astype(str).unique())
        raise ValueError(f"tickets contains unsupported data_split values: {values}")

    # The reply language and the source-message language are distinct fields.
    for column in ("language", "body_language"):
        normalized = tickets[column].astype("string").str.strip().str.lower()
        invalid_codes = normalized.notna() & ~normalized.str.fullmatch(r"[a-z]{2}").fillna(False)
        if invalid_codes.any():
            raise ValueError(f"tickets contains invalid ISO 639-1 codes in {column}")
        tickets[column] = normalized

    email_values = tickets["contact_email_masked"].astype("string").str.strip()
    present_emails = email_values.notna() & email_values.ne("")
    masked_emails = email_values.str.contains("***", regex=False, na=False)
    unmasked_emails = present_emails & ~masked_emails
    if unmasked_emails.any():
        raise ValueError(
            "contact_email_masked contains "
            f"{int(unmasked_emails.sum())} non-empty values without a mask marker"
        )

    language_mismatch = (
        tickets["language"].notna()
        & tickets["body_language"].notna()
        & tickets["language"].ne(tickets["body_language"])
    )
    language_mismatch_count = int(language_mismatch.sum())

    ticket_splits = tickets.set_index("ticket_id")["data_split"]
    unknown_case_tickets = ~cases["ticket_id"].isin(ticket_splits.index)
    if unknown_case_tickets.any():
        raise ValueError(
            "resolution_cases references "
            f"{int(unknown_case_tickets.sum())} ticket IDs absent from tickets"
        )

    tickets_by_split = {
        split: tickets.loc[tickets["data_split"].eq(split)].reset_index(drop=True)
        for split in SPLITS
    }
    train_ticket_ids = set(tickets_by_split["train"]["ticket_id"])
    holdout_ticket_ids = set(tickets_by_split["valid"]["ticket_id"]) | set(
        tickets_by_split["test"]["ticket_id"]
    )
    cases_seed = cases.loc[cases["ticket_id"].isin(train_ticket_ids)].reset_index(drop=True)
    holdout_cases_removed = int(cases["ticket_id"].isin(holdout_ticket_ids).sum())

    train = tickets_by_split["train"]
    subject = train["inquiry_subject"].fillna("").astype("string").str.strip()
    body = train["inquiry_body"].fillna("").astype("string").str.strip()
    text = subject.str.cat(body, sep="\n").str.strip()
    labels = train["category_code"].astype("string").str.strip()
    missing_labels = labels.isna() | labels.eq("")
    if missing_labels.any():
        raise ValueError(f"train contains {int(missing_labels.sum())} rows without category_code")

    has_text = text.ne("")
    classifier_train = pd.DataFrame(
        {"text": text.loc[has_text], "category_code": labels.loc[has_text]}
    ).reset_index(drop=True)

    return PreparedDatasets(
        tickets_by_split=tickets_by_split,
        cases_seed=cases_seed,
        classifier_train=classifier_train,
        ticket_duplicates_removed=ticket_duplicates_removed,
        case_duplicates_removed=case_duplicates_removed,
        holdout_cases_removed=holdout_cases_removed,
        masked_email_count=int(masked_emails.sum()),
        email_value_count=int(present_emails.sum()),
        language_mismatch_count=language_mismatch_count,
    )


def main() -> None:
    if not INPUT_PATH.is_file():
        raise FileNotFoundError(f"Input workbook not found: {INPUT_PATH}")

    sheets = pd.read_excel(INPUT_PATH, sheet_name=["tickets", "resolution_cases"])
    prepared = prepare_datasets(sheets["tickets"], sheets["resolution_cases"])

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for split, frame in prepared.tickets_by_split.items():
        frame.to_parquet(OUTPUT_DIR / f"tickets_{split}.parquet", index=False)
    prepared.cases_seed.to_parquet(OUTPUT_DIR / "cases_seed.parquet", index=False)
    prepared.classifier_train.to_parquet(OUTPUT_DIR / "classifier_train.parquet", index=False)

    resolved_train_count = int(prepared.tickets_by_split["train"]["resolved_at_utc"].notna().sum())
    print(
        "tickets: "
        f"train={len(prepared.tickets_by_split['train'])}, "
        f"valid={len(prepared.tickets_by_split['valid'])}, "
        f"test={len(prepared.tickets_by_split['test'])}, "
        f"duplicates_removed={prepared.ticket_duplicates_removed}"
    )
    print(
        "resolution_cases: "
        f"input={len(sheets['resolution_cases'])}, "
        f"cases_seed={len(prepared.cases_seed)}, "
        f"valid_test_excluded={prepared.holdout_cases_removed}, "
        f"duplicates_removed={prepared.case_duplicates_removed}"
    )
    print(
        f"classifier_train={len(prepared.classifier_train)}, "
        f"resolved_train_tickets={resolved_train_count}"
    )
    print(
        f"masked contact emails={prepared.masked_email_count}/"
        f"{prepared.email_value_count}, "
        f"language/body_language mismatches={prepared.language_mismatch_count}"
    )
    print(f"Parquet files written to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
