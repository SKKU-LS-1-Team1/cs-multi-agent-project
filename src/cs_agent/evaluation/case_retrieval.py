# 해결 사례 찾기 비교: 지난 문의 임베딩 vs 패턴 DB (CSA-28 · 피드백 "임베딩이 맞는지 근거 필요")
#
# 질문: 새 문의에 맞는 '이미 처리된 문의'를 무엇으로 찾아야 하나.
# 정답: split 문의 중 해결 사례가 연결된 것. 찾은 근거의 고장(fault_id)이 그 문의의 실제 사례와
#   같으면 맞음 (같은 고장 = 같은 원인·조치). 사례 DB 는 train 사례 568건 (cases_seed).
# 비교 — 모두 운영 코드 그대로 (retrieval.first_pass 의 cases 검색 → finalize_evidence → 위 2개):
#   case_embed : 바꾸기 전. 지난 문의 글 임베딩(resolution_cases.embedding) 코사인 상위 3
#   frequency  : 패턴, 메타데이터가 맞는 것 중 해결 건수 많은 순 (임베딩 없음)
#   pattern    : 지금. 패턴 설명 임베딩(case_patterns) 상위 8 → 제품군·적용 제품·에러코드로 거름
# 메타데이터 (finalize_evidence 에 넘기는 유형·제품·제품군·에러코드)
#   gold : 티켓 라벨 (분석이 맞았을 때)
#   rule : LLM 없는 규칙 추출 제품·에러코드 + 라벨 유형 (분석 정확도는 CSA-26 평가에서 따로)
#
# 실행 (pgvector 에 사례·패턴이 적재돼 있어야 한다: pipeline.embed_docs --target all)
#   DATABASE_URL=... uv run --extra llm --extra data python -m cs_agent.evaluation.case_retrieval
#   --split valid|test, --out 결과.json
import argparse
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
K = 2  # 초안에 들어가는 사례 수 (retrieval.FINAL_CASES_K)


def _s(value) -> str:
    """CSV 빈 칸(NaN)은 빈 문자열."""
    return value if isinstance(value, str) else ""


def load(split: str):
    import pandas as pd

    raw = pd.read_csv(ROOT / "data/raw/resolution_cases.csv", dtype=str)
    tickets = pd.read_csv(ROOT / "data/raw/tickets.csv", dtype=str)
    seed = pd.read_parquet(ROOT / "data/processed/cases_seed.parquet")
    queries = tickets[tickets.data_split == split].merge(
        raw[["ticket_id", "fault_id"]], on="ticket_id"
    )
    return queries, seed


def gold_metadata(row) -> dict:
    return {
        "category": row.category_code,
        "product_code": _s(row.product_code) or None,
        "product_family": _s(row.product_family) or None,
        "error_code": _s(row.error_code_reported) or None,
    }


def rule_metadata(row) -> dict:
    """LLM 없는 규칙 추출 (제품·에러코드). 유형은 라벨."""
    from cs_agent.agents.analysis import extract_details
    from cs_agent.rules.tables import load_tables
    from cs_agent.schemas import InquiryIn

    inquiry = InquiryIn(
        channel=row.channel if row.channel in ("EMAIL", "WEB", "CHAT", "PHONE") else "EMAIL",
        language=_s(row.language) or "en",
        subject=_s(row.inquiry_subject),
        body=_s(row.inquiry_body),
    )
    d = extract_details(inquiry, load_tables(), llm=None, category=row.category_code)
    return {
        "category": row.category_code,
        "product_code": d.product_code,
        "product_family": d.product_family,
        "error_code": d.error_code,
    }


def _final_faults(candidates, meta, fault_of) -> list[str]:
    """운영과 같은 근거 확정 → 위 K개 사례 근거의 고장."""
    from cs_agent.agents.retrieval import finalize_evidence
    from cs_agent.schemas import Extraction

    extraction = Extraction(
        product_code=meta["product_code"],
        product_family=meta["product_family"],
        error_code=meta["error_code"],
    )
    final = finalize_evidence(candidates, extraction, category=meta["category"])
    return [fault_of(e) for e in final if e.source == "cases"][:K]


def _frequency(meta, seed) -> list[str]:
    """메타데이터가 맞는 고장 중 해결 건수 많은 순 (같은 유형 먼저)."""
    pool = seed[seed.product_family == meta["product_family"]] if meta["product_family"] else seed
    code = (meta["error_code"] or "").upper()
    if code and (pool.error_code.fillna("").str.upper() == code).any():
        pool = pool[pool.error_code.fillna("").str.upper() == code]
    counts = pool.groupby("fault_id").agg(
        n=("case_id", "size"), same=("category_code", lambda c: (c == meta["category"]).sum())
    )
    return list(counts.sort_values(["same", "n"], ascending=False).index[:K])


def main(argv: list[str] | None = None) -> None:
    from cs_agent.agents.case_patterns import PgPatternRetriever
    from cs_agent.agents.retrieval import CASES_K, PgVectorRetriever
    from cs_agent.pipeline.embed_docs import embed

    parser = argparse.ArgumentParser(description="해결 사례 찾기: 지난 문의 임베딩 vs 패턴 DB")
    parser.add_argument("--split", default="valid")
    parser.add_argument("--out", type=Path, help="결과 JSON 저장 경로")
    args = parser.parse_args(argv)

    queries, seed = load(args.split)
    fault_of_case = dict(zip(seed.case_id, seed.fault_id, strict=True))
    seen = set(seed.fault_id)
    texts = {
        row.ticket_id: f"{_s(row.inquiry_subject)}\n{_s(row.inquiry_body)}".strip()
        for row in queries.itertuples()
    }
    # 문의 임베딩은 적재와 같은 embed() 로 한 번만 만들어 두 검색기가 같이 쓴다
    vectors = dict(zip(texts.values(), embed(list(texts.values())), strict=True))
    old = PgVectorRetriever("resolution_cases", embed_fn=vectors.__getitem__)
    new = PgPatternRetriever(embed_fn=vectors.__getitem__)
    old_top = {t: old.search(q, 3) for t, q in texts.items()}  # 바꾸기 전 CASES_K = 3
    new_top = {t: new.search(q, CASES_K) for t, q in texts.items()}

    results: dict = {"split": args.split, "k": K}
    for variant, meta_of in (("gold", gold_metadata), ("rule", rule_metadata)):
        hits: Counter = Counter()
        for row in queries.itertuples():
            meta, gold = meta_of(row), row.fault_id
            ranked = {
                "case_embed": _final_faults(
                    old_top[row.ticket_id], meta, lambda e: fault_of_case.get(e.doc_id)
                ),
                "frequency": _frequency(meta, seed),
                "pattern": _final_faults(
                    new_top[row.ticket_id], meta, lambda e: e.metadata["pattern_id"]
                ),
            }
            hits["n"] += 1
            hits["reachable"] += gold in seen
            for name, faults in ranked.items():
                hits[f"{name}@1"] += faults[:1] == [gold]
                hits[f"{name}@{K}"] += gold in faults
            old_faults = ranked["case_embed"]
            hits["case_embed_top2_same_fault"] += len(old_faults) == K and len(set(old_faults)) == 1
            top1 = old_top[row.ticket_id][:1]
            if top1 and fault_of_case.get(top1[0].doc_id) != gold:
                hits["case_embed_top1_wrong"] += 1
                hits["case_embed_top1_wrong_same_product"] += (
                    top1[0].metadata.get("product_code") == row.product_code
                )
        results[variant] = dict(hits)

    print(json.dumps(results, ensure_ascii=False, indent=2))
    if args.out:
        args.out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
