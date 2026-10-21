# 문의 전환 기준값 측정 (CSA-35 · 담당 박종석)
# 실행 예: LLM_PROVIDER=live uv run --extra llm --extra data \
#            python -m cs_agent.evaluation.handoff_threshold --split valid
#
# chatbot/handoff.py 의 MIN_RETRIEVAL_SCORE 근거를 다시 낸다. 임베딩 모델·차원이나 문서 글 모양
# (pipeline/chunking.py Chunk.embedding_text, embed_docs.doc_rows)이 바뀌면 다시 돌린다.
#
# - 문서: 적재와 같은 embed_docs.doc_rows() 의 text 를 embed_docs.embed() 로 임베딩
# - 답이 있는 질문: tickets.csv 의 split 문의, 글은 그래프 검색과 같은 "제목\n본문"
# - 답이 없는 질문: data/eval/handoff_out_of_scope.txt (가전·여행·채용·날씨·없는 제품 등 16개 언어)
# - 점수: docs 1등 cosine 유사도 (= PgVectorRetriever score, 제품 필터 없음)
# - 결정 유형(handoff.DECISION_CATEGORIES)은 점수와 상관없이 넘어가므로 따로 본다.
#
# 임베딩은 data/processed/handoff_embed_cache.json 에 모델·차원·글 기준으로 캐시한다 (git 제외).
# 문서 813 + valid 603 + 범위 밖 48 ≈ 1,460회 호출, 캐시가 있으면 바뀐 글만 다시 부른다.
import argparse
import csv
import hashlib
import json
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cs_agent.chatbot.handoff import DECISION_CATEGORIES, MIN_RETRIEVAL_SCORE
from cs_agent.config import REPO_ROOT, get_settings

OUT_OF_SCOPE_PATH = REPO_ROOT / "data" / "eval" / "handoff_out_of_scope.txt"
CACHE_PATH = REPO_ROOT / "data" / "processed" / "handoff_embed_cache.json"
HIST_BINS = [round(0.40 + 0.05 * i, 2) for i in range(12)]  # 0.40 ~ 0.95
SWEEP = [round(0.60 + 0.02 * i, 2) for i in range(9)]  # 0.60 ~ 0.76
WORKERS = 6


@dataclass
class Summary:
    valid_n: int
    valid_min: float
    valid_p5: float
    valid_median: float
    answerable_n: int  # 결정 유형을 뺀 valid (점수 기준으로만 갈리는 질문)
    answerable_min: float
    out_of_scope_n: int
    out_of_scope_max: float
    out_of_scope_median: float
    hit_rate: float  # 정답 문서가 top-3 안 (임베딩만, 재정렬 없음)
    miss_median: float

    @property
    def gap(self) -> tuple[float, float]:
        """범위 밖 최고점 ~ 답이 있는 질문 최저점. 앞이 뒤보다 작아야 빈 구간이 있다."""
        return self.out_of_scope_max, self.answerable_min

    def separates(self, threshold: float) -> bool:
        return self.out_of_scope_max < threshold <= self.answerable_min


def _percentile(values: Sequence[float], q: float) -> float:
    import numpy as np

    return float(np.percentile(values, q))


def summarize(
    valid_best: Sequence[float],
    valid_categories: Sequence[str],
    valid_hit: Sequence[bool],
    out_of_scope_best: Sequence[float],
) -> Summary:
    decision = {str(c) for c in DECISION_CATEGORIES}
    answerable = [s for s, c in zip(valid_best, valid_categories, strict=True) if c not in decision]
    misses = [s for s, h in zip(valid_best, valid_hit, strict=True) if not h]
    return Summary(
        valid_n=len(valid_best),
        valid_min=min(valid_best),
        valid_p5=_percentile(valid_best, 5),
        valid_median=_percentile(valid_best, 50),
        answerable_n=len(answerable),
        answerable_min=min(answerable),
        out_of_scope_n=len(out_of_scope_best),
        out_of_scope_max=max(out_of_scope_best),
        out_of_scope_median=_percentile(out_of_scope_best, 50),
        hit_rate=sum(valid_hit) / len(valid_hit),
        miss_median=_percentile(misses, 50) if misses else 0.0,
    )


def _cache_key(text: str) -> str:
    settings = get_settings()
    raw = f"{settings.embedding_model}|{settings.embedding_dim}|{text}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def embed_cached(texts: Sequence[str], cache_path: Path = CACHE_PATH) -> Any:
    """글마다 정규화한 임베딩 행렬. 캐시에 없는 글만 embed_docs.embed 로 부른다."""
    import numpy as np

    from cs_agent.pipeline.embed_docs import embed

    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    todo = sorted({t for t in texts if _cache_key(t) not in cache})
    print(f"  임베딩 {len(todo)}건 (캐시 {len(texts) - len(todo)}건)", flush=True)
    with ThreadPoolExecutor(WORKERS) as pool:
        for i, (text, vector) in enumerate(
            zip(todo, pool.map(lambda t: embed([t])[0], todo), strict=True), 1
        ):
            cache[_cache_key(text)] = vector
            if i % 100 == 0 or i == len(todo):
                print(f"    {i}/{len(todo)}", flush=True)
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                cache_path.write_text(json.dumps(cache))
    matrix = np.array([cache[_cache_key(t)] for t in texts], dtype=np.float32)
    return matrix / np.linalg.norm(matrix, axis=1, keepdims=True)


def _report(summary: Summary, valid_best: Any, out_of_scope_best: Any, valid_cat: list[str]) -> str:
    import numpy as np

    decision = {str(c) for c in DECISION_CATEGORIES}
    answerable = np.array(
        [s for s, c in zip(valid_best, valid_cat, strict=True) if c not in decision]
    )
    lines = [
        f"embedding={get_settings().embedding_model}·{get_settings().embedding_dim}",
        "",
        "| 집합 | n | 최저 | 하위 5% | 중앙값 | 최고 |",
        "|---|---|---|---|---|---|",
        f"| valid 전체 | {summary.valid_n} | {summary.valid_min:.3f} | {summary.valid_p5:.3f} | "
        f"{summary.valid_median:.3f} | {max(valid_best):.3f} |",
        f"| valid 중 결정 유형 제외 | {summary.answerable_n} | **{summary.answerable_min:.3f}** | "
        f"{_percentile(answerable, 5):.3f} | {_percentile(answerable, 50):.3f} | "
        f"{answerable.max():.3f} |",
        f"| 범위 밖 질문 | {summary.out_of_scope_n} | {min(out_of_scope_best):.3f} | "
        f"{_percentile(out_of_scope_best, 5):.3f} | {summary.out_of_scope_median:.3f} | "
        f"**{summary.out_of_scope_max:.3f}** |",
        "",
        f"top-3 정답 (임베딩만) {summary.hit_rate:.1%}, 정답 못 찾은 건 1등 점수 중앙값 "
        f"{summary.miss_median:.3f}",
        "",
        "```",
        "1등 점수     valid   범위 밖",
    ]
    valid_hist, _ = np.histogram(valid_best, HIST_BINS)
    oos_hist, _ = np.histogram(out_of_scope_best, HIST_BINS)
    for low, high, v, o in zip(HIST_BINS, HIST_BINS[1:], valid_hist, oos_hist, strict=False):
        lines.append(f"{low:.2f}-{high:.2f}  {v:>4} {'#' * (v // 8):<40} {o:>3} {'o' * o}")
    lines += [
        "```",
        "",
        "| 기준 | 결정 유형 외 valid 유지 | 범위 밖 전환 |",
        "|---|---|---|",
    ]
    for t in SWEEP:
        mark = (
            " ← 현재"
            if MIN_RETRIEVAL_SCORE is not None and abs(t - MIN_RETRIEVAL_SCORE) < 1e-9
            else ""
        )
        lines.append(
            f"| {t:.2f}{mark} | {np.mean(answerable >= t):.1%} | "
            f"{np.mean(np.asarray(out_of_scope_best) < t):.1%} |"
        )
    low, high = summary.gap
    lines += [
        "",
        f"빈 구간: 범위 밖 최고 {low:.3f} < 결정 유형 외 valid 최저 {high:.3f}"
        if low < high
        else f"⚠️ 빈 구간 없음: 범위 밖 최고 {low:.3f} ≥ 결정 유형 외 valid 최저 {high:.3f}",
    ]
    if MIN_RETRIEVAL_SCORE is not None:
        ok = summary.separates(MIN_RETRIEVAL_SCORE)
        lines.append(
            f"현재 MIN_RETRIEVAL_SCORE={MIN_RETRIEVAL_SCORE:.2f}: "
            + (
                f"구간 안 (여유 {MIN_RETRIEVAL_SCORE - low:.3f} / {high - MIN_RETRIEVAL_SCORE:.3f})"
                if ok
                else "⚠️ 구간 밖 — 기준값을 다시 정해야 한다"
            )
        )
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> None:
    import numpy as np

    from cs_agent.pipeline.chunking import iter_doc_chunks
    from cs_agent.pipeline.embed_docs import doc_rows

    parser = argparse.ArgumentParser(description="문의 전환 기준값(MIN_RETRIEVAL_SCORE) 측정")
    parser.add_argument("--split", default="valid", choices=("train", "valid"))
    parser.add_argument("--json", type=Path, help="점수 원본을 저장할 경로")
    args = parser.parse_args(argv)

    docs = doc_rows(iter_doc_chunks())
    with (get_settings().raw_data_dir / "tickets.csv").open(encoding="utf-8-sig") as f:
        tickets = [r for r in csv.DictReader(f) if r["data_split"] == args.split]
    queries = [f"{r['inquiry_subject']}\n{r['inquiry_body']}".strip() for r in tickets]
    out_of_scope = [
        line.strip() for line in OUT_OF_SCOPE_PATH.read_text(encoding="utf-8").splitlines()
    ]
    out_of_scope = [q for q in out_of_scope if q]

    print(f"문서 {len(docs)}조각 · {args.split} {len(queries)}건 · 범위 밖 {len(out_of_scope)}건")
    doc_matrix = embed_cached([d["text"] for d in docs])
    query_sim = embed_cached(queries) @ doc_matrix.T
    oos_best = (embed_cached(out_of_scope) @ doc_matrix.T).max(axis=1)
    valid_best = query_sim.max(axis=1)

    hits = []
    for i, row in enumerate(tickets):
        top = np.argsort(-query_sim[i])[:3]
        ref, section = row["reference_doc_id"], row["reference_section"]
        hits.append(
            bool(ref)
            and any(
                docs[j]["doc_id"] == ref and (not section or docs[j]["section"] == section)
                for j in top
            )
        )
    categories = [r["category_code"] for r in tickets]
    summary = summarize(valid_best.tolist(), categories, hits, oos_best.tolist())
    print()
    print(_report(summary, valid_best, oos_best, categories))
    if args.json:
        args.json.write_text(
            json.dumps(
                {
                    "valid_best": valid_best.tolist(),
                    "valid_category": categories,
                    "valid_hit": hits,
                    "out_of_scope": dict(zip(out_of_scope, oos_best.tolist(), strict=True)),
                },
                ensure_ascii=False,
                indent=1,
            )
        )


if __name__ == "__main__":
    main()
