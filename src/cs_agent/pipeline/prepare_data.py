"""상담 이력 정제, 학습·시험 분리 (CSA-17 · 담당 박종석).

입력: data/raw/cs_tickets_resolution_v1.xlsx (tickets 4000 · resolution_cases 800)
출력: data/processed/{tickets_train,tickets_valid,tickets_test,cases_seed}.parquet

규칙
- data_split 열을 그대로 쓴다 (train 2800 / valid 603 / test 597).
- resolution_cases 중 valid·test 티켓에 연결된 사례는 사례 DB 처음 적재에서 뺀다 (N-05).

실행: `uv run --extra data python -m cs_agent.pipeline.prepare_data`
"""

from cs_agent.config import get_settings


def main() -> None:
    import pandas as pd  # extra: data

    s = get_settings()
    src = s.raw_data_dir / "cs_tickets_resolution_v1.xlsx"
    out = s.raw_data_dir.parent / "processed"
    out.mkdir(parents=True, exist_ok=True)

    tickets = pd.read_excel(src, sheet_name="tickets")
    cases = pd.read_excel(src, sheet_name="resolution_cases")
    # TODO(CSA-17): 정제 규칙 (중복 제거, 언어 정규화, 마스킹 확인)
    for split in ("train", "valid", "test"):
        tickets[tickets["data_split"] == split].to_parquet(out / f"tickets_{split}.parquet")

    held_out = set(tickets.loc[tickets["data_split"] != "train", "resolution_case_id"].dropna())
    seed = cases[~cases["case_id"].isin(held_out)] if "case_id" in cases else cases
    seed.to_parquet(out / "cases_seed.parquet")
    print(f"tickets={len(tickets)} cases_seed={len(seed)} (held out {len(held_out)})")


if __name__ == "__main__":
    main()
