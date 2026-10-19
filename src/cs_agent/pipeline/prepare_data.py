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

# config.Settings.raw_data_dir 가 생기면(CSA-21) 그 값을 쓴다.
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
# 엑셀은 dtype=str 로 읽는다 (펌웨어 버전·절 번호 '3.10' 이 3.1 이 되지 않게).
# 아래 시간·횟수 열만 숫자로 되돌린다 (SLA 목표 시간 대조 등에 쓴다).
NUMERIC_COLUMNS = (
    "first_response_hours",
    "customer_wait_hours",
    "customer_followups",
    "sla_first_response_target_h",
    "sla_resolution_target_h",
    "sla_elapsed_hours",
    "time_to_resolve_hours",
)
# 본문에 남은 연락처: 이메일, 국가번호(+)로 시작하는 전화번호. 날짜·IEC 규격 번호는 제외된다.
BODY_CONTACT_PATTERN = r"[\w.+-]+@[\w-]+\.[\w.]+|\+\d[\d\s().-]{7,}\d"


@dataclass(frozen=True)
class PreparedDatasets:
    tickets_by_split: dict[str, pd.DataFrame]
    cases_seed: pd.DataFrame
    classifier_train: pd.DataFrame
    ticket_duplicates_removed: int
    case_duplicates_removed: int
    cases_excluded: int
    train_text_leaks_removed: int
    holdout_text_overlaps: int
    masked_email_count: int
    email_value_count: int
    body_contact_count: int
    invalid_language_count: int
    language_mismatch_count: int


def _require_columns(frame: pd.DataFrame, required: set[str], name: str) -> None:
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"{name} sheet is missing required columns: {', '.join(missing)}")


def _to_numeric(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.copy()
    for column in NUMERIC_COLUMNS:
        if column in frame.columns:
            frame[column] = pd.to_numeric(frame[column])
    return frame


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


def _normalize_language(values: pd.Series) -> tuple[pd.Series, int]:
    """'EN ', 'zh-CN', 'pt_BR' → 'en', 'zh', 'pt'. ISO 639-1 로 못 읽는 값은 비우고 개수를 센다."""
    normalized = values.astype("string").str.strip().str.lower().str.split(r"[-_]").str[0]
    normalized = normalized.mask(normalized.eq(""))
    invalid = normalized.notna() & ~normalized.str.fullmatch(r"[a-z]{2}").fillna(False)
    return normalized.mask(invalid), int(invalid.sum())


def _text_key(tickets: pd.DataFrame) -> pd.Series:
    """제목+본문 비교 키. 대소문자·공백 차이는 같은 문의로 본다."""
    subject = tickets["inquiry_subject"].fillna("").astype("string")
    body = tickets["inquiry_body"].fillna("").astype("string")
    text = subject.str.cat(body, sep="\n").str.casefold()
    return text.str.replace(r"\s+", " ", regex=True).str.strip()


def prepare_datasets(tickets: pd.DataFrame, cases: pd.DataFrame) -> PreparedDatasets:
    _require_columns(tickets, TICKET_COLUMNS, "tickets")
    _require_columns(cases, CASE_COLUMNS, "resolution_cases")

    tickets, ticket_duplicates_removed = _deduplicate(_to_numeric(tickets), "ticket_id", "tickets")
    cases, case_duplicates_removed = _deduplicate(_to_numeric(cases), "case_id", "resolution_cases")
    cases["ticket_id"] = cases["ticket_id"].astype("string").str.strip()

    # 표기만 흔들리는 값은 정리한다. 정리해도 어느 split 인지 모르는 행은 나눌 수 없어 멈춘다.
    tickets["data_split"] = tickets["data_split"].astype("string").str.strip().str.lower()
    invalid_splits = tickets["data_split"].isna() | ~tickets["data_split"].isin(SPLITS)
    if invalid_splits.any():
        values = sorted(tickets.loc[invalid_splits, "data_split"].astype(str).unique())
        raise ValueError(f"tickets contains unsupported data_split values: {values}")

    # The reply language and the source-message language are distinct fields.
    invalid_language_count = 0
    for column in ("language", "body_language"):
        tickets[column], invalid_count = _normalize_language(tickets[column])
        invalid_language_count += invalid_count

    tickets["category_code"] = tickets["category_code"].astype("string").str.strip()

    email_values = tickets["contact_email_masked"].astype("string").str.strip()
    present_emails = email_values.notna() & email_values.ne("")
    masked_emails = email_values.str.contains("***", regex=False, na=False)
    unmasked_emails = present_emails & ~masked_emails
    if unmasked_emails.any():
        raise ValueError(
            "contact_email_masked contains "
            f"{int(unmasked_emails.sum())} non-empty values without a mask marker"
        )
    body_contact_count = int(
        tickets["inquiry_body"].astype("string").str.contains(BODY_CONTACT_PATTERN, na=False).sum()
    )

    language_mismatch = (
        tickets["language"].notna()
        & tickets["body_language"].notna()
        & tickets["language"].ne(tickets["body_language"])
    )
    language_mismatch_count = int(language_mismatch.sum())

    unknown_case_tickets = ~cases["ticket_id"].isin(tickets["ticket_id"])
    if unknown_case_tickets.any():
        raise ValueError(
            "resolution_cases references "
            f"{int(unknown_case_tickets.sum())} ticket IDs absent from tickets"
        )

    # valid·test 와 제목+본문이 같은 train 티켓은 뺀다 (N-05). 평가셋은 그대로 둔다.
    text_key = _text_key(tickets)
    is_train = tickets["data_split"].eq("train")
    holdout_keys = text_key.loc[~is_train]
    train_leaks = is_train & text_key.isin(holdout_keys)
    holdout_text_overlaps = int(holdout_keys.duplicated(keep=False).sum())
    tickets = tickets.loc[~train_leaks]

    tickets_by_split = {
        split: tickets.loc[tickets["data_split"].eq(split)].reset_index(drop=True)
        for split in SPLITS
    }
    train = tickets_by_split["train"]
    cases_seed = cases.loc[cases["ticket_id"].isin(train["ticket_id"])].reset_index(drop=True)

    subject = train["inquiry_subject"].fillna("").astype("string").str.strip()
    body = train["inquiry_body"].fillna("").astype("string").str.strip()
    text = subject.str.cat(body, sep="\n").str.strip()
    labels = train["category_code"]
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
        cases_excluded=len(cases) - len(cases_seed),
        train_text_leaks_removed=int(train_leaks.sum()),
        holdout_text_overlaps=holdout_text_overlaps,
        masked_email_count=int(masked_emails.sum()),
        email_value_count=int(present_emails.sum()),
        body_contact_count=body_contact_count,
        invalid_language_count=invalid_language_count,
        language_mismatch_count=language_mismatch_count,
    )


def main() -> None:
    if not INPUT_PATH.is_file():
        raise FileNotFoundError(f"Input workbook not found: {INPUT_PATH}")

    sheets = pd.read_excel(INPUT_PATH, sheet_name=["tickets", "resolution_cases"], dtype=str)
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
        f"duplicates_removed={prepared.ticket_duplicates_removed}, "
        f"train_text_leaks_removed={prepared.train_text_leaks_removed}, "
        f"valid_test_text_overlaps={prepared.holdout_text_overlaps}"
    )
    print(
        "resolution_cases: "
        f"input={len(sheets['resolution_cases'])}, "
        f"cases_seed={len(prepared.cases_seed)}, "
        f"excluded={prepared.cases_excluded}, "
        f"duplicates_removed={prepared.case_duplicates_removed}"
    )
    print(
        f"classifier_train={len(prepared.classifier_train)}, "
        f"resolved_train_tickets={resolved_train_count}"
    )
    print(
        f"masked contact emails={prepared.masked_email_count}/"
        f"{prepared.email_value_count}, "
        f"unmasked contacts in body={prepared.body_contact_count}, "
        f"invalid language codes={prepared.invalid_language_count}, "
        f"language/body_language mismatches={prepared.language_mismatch_count}"
    )
    print(f"Parquet files written to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
