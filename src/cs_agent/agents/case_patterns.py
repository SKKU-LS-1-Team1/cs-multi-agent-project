# 해결 사례 패턴 DB (CSA-28)
# 피드백: "처리된 문의를 학습할 때 패턴 DB 를 쓰라, 임베딩이 맞는지 근거가 필요하다"
#
# 처리된 문의를 문의 글 그대로 임베딩해 두고 새 문의와 코사인 유사도로 찾던 것을 바꾼다.
# 해결된 문의는 '패턴'으로 묶어 배운다. 패턴 하나 = 같은 고장(같은 원인 · 조치).
#   - 고장 카탈로그(fault_catalog.csv) 행이 패턴이다 (pattern_id = fault_id). 확정된 원인이
#     카탈로그 원인과 같으면 그 패턴 (train 568건 모두 같다 — 제품군 안에서 원인 → fault 1:1).
#   - 카탈로그에 없는 원인으로 해결되면 새 패턴 LIVE-<제품군>-<원인 해시> 를 만든다.
# 학습 (해결 확정, services/tickets.resolve → case_memory.build_case → records.save_case):
#   사례에 pattern_id 를 붙여 저장한다. 패턴의 해결 건수 · 대표 사례(최근 해결, 운영 사례 먼저)는
#   active 사례로 센다 — 재문의로 다시 열린 사례(active=false)는 바로 빠진다.
# 찾기 (retrieval.first_pass 의 cases 자리): 새 문의를 '패턴 설명'(증상 · 원인 · 진단 · 조치)과
#   비교한다. 해결된 적 있는 패턴만. 근거 확정(finalize_evidence)에서 제품군 · 적용 제품 ·
#   에러코드로 거르고 위 2개를 초안에 넣는다 (문장 본보기는 대표 사례의 최종 답변).
#   임베딩은 패턴 설명에만 한다 (패턴 수만큼, 97개 + 운영 패턴).
#   지난 문의 글은 임베딩해서 찾지 않는다.
#
# 근거 (evaluation/case_retrieval.py — 운영 코드 그대로 first_pass → finalize_evidence → 위 2개.
#   정답 = 문의에 연결된 실제 해결 사례와 같은 고장(fault_id). 사례 DB = train 568건)
#                                            valid 128건          test 104건 (조정에 안 씀)
#   방식                                     1등   위 2개 안      1등   위 2개 안
#   지난 문의 글 임베딩 (바꾸기 전)            86       94          77       85
#   패턴, 해결 건수 많은 순 (임베딩 없음)       37       56          42       57
#   패턴 설명 임베딩 + 거름 (지금)              90      109          83       93
#   - 규칙 추출 메타데이터(LLM 없음)로 재도 같다.
#   - 지난 문의 임베딩의 1등 오답 36건 중 34건이 '같은 제품의 다른 고장'이다. 같은 제품 문의끼리
#     글(제품명 · 문체 · 템플릿)이 비슷해 증상 차이보다 그쪽이 유사도를 정한다 (피드백의 '왜곡').
#   - 위 2개가 같은 고장인 경우가 74/128 — 비슷한 지난 문의가 몰려 두 번째 자리를 버린다.
#     패턴으로 묶으면 서로 다른 고장 2개가 들어간다.
#   - 임베딩을 아예 빼면(해결 건수 순) 크게 나빠진다: 같은 제품군 · 유형 안에 고장이 보통 3개
#     (많으면 14개)라 증상을 봐야 가를 수 있다. 그래서 증상은 '패턴 설명'과 비교한다.
#     해결 건수를 순위에 섞어도 나빠졌다 (탐색: 가중 0.01 → 위 2개 102, 0.04 → 97). 건수는 근거
#     글에만 적는다.
#   - 재현: DATABASE_URL=… uv run --extra llm --extra data \
#       python -m cs_agent.evaluation.case_retrieval --split valid (--split test)
import hashlib
import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from functools import lru_cache
from pathlib import Path
from typing import Any

from cs_agent.schemas import Evidence

LIVE_PREFIX = "LIVE-"
EXAMPLE_CHARS = 1200  # 근거에 넣는 대표 사례 답변 길이


def _norm(text: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def _code(value: Any) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text.upper() if text and text.lower() != "nan" else None


def describe(
    family: str,
    error_code: str | None,
    symptom: str,
    cause: str,
    action: str,
    diagnosis: str = "",
) -> str:
    """패턴 설명 = 임베딩하는 글."""
    head = f"Fault pattern: {family}" + (f" · error {error_code}" if error_code else "")
    parts = [
        head,
        f"Symptom: {symptom}",
        f"Cause: {cause}",
        f"Diagnosis: {diagnosis}",
        f"Action: {action}",
    ]
    return "\n".join(p for p in parts if not p.endswith(": "))


@lru_cache(maxsize=1)
def _catalog() -> tuple[dict[str, dict], dict[tuple[str, str], str]]:
    from cs_agent.rules.tables import load_tables

    faults = {r["fault_id"]: r for r in load_tables().faults}
    by_cause = {(r["family"], _norm(r["root_cause"])): fid for fid, r in faults.items()}
    return faults, by_cause


def catalog_rows() -> list[dict]:
    """case_patterns 의 카탈로그 행 (pipeline/embed_docs.py 가 적재)."""
    return [dict(r) for r in _catalog_rows().values()]


@lru_cache(maxsize=1)
def _catalog_rows() -> dict[str, dict]:
    rows = {}
    for fid, r in _catalog()[0].items():
        code = _code(r.get("error_code"))
        rows[fid] = {
            "pattern_id": fid,
            "family": r["family"],
            "error_code": code,
            "applies_to": [p for p in (r.get("applies_to") or "").split(";") if p],
            "text": describe(
                r["family"],
                code,
                r.get("symptom", ""),
                r.get("root_cause", ""),
                r.get("action", ""),
                r.get("diagnosis", ""),
            ),
            "source": "catalog",
        }
    return rows


def assign_pattern(family: str | None, cause: str | None) -> str | None:
    """확정된 원인 → pattern_id. 카탈로그 원인과 같으면 fault_id, 아니면 LIVE-<제품군>-<해시>.

    원인이 없는 예전 방식 해결(본문 없는 resolve — 평가 시연)은 부르는 쪽이 문의 요약을 넘긴다.
    글이 비면 None (패턴으로 배우지 않는다).
    """
    if not _norm(cause):
        return None
    fid = _catalog()[1].get((family or "", _norm(cause)))
    if fid:
        return fid
    digest = hashlib.sha1(_norm(cause).encode()).hexdigest()[:10]
    return f"{LIVE_PREFIX}{family or 'ANY'}-{digest}"


def pattern_row(case: Mapping[str, Any]) -> dict | None:
    """사례의 패턴 행. 카탈로그 패턴이면 카탈로그 설명, LIVE 면 사례의 확정 원인 · 조치로 만든다."""
    pattern_id = case.get("pattern_id") or assign_pattern(
        case.get("product_family"), case.get("cause") or case.get("summary")
    )
    if not pattern_id:
        return None
    if not pattern_id.startswith(LIVE_PREFIX):
        row = _catalog_rows().get(pattern_id)
        return dict(row) if row else None
    family = case.get("product_family") or ""
    code = _code(case.get("error_code"))
    return {
        "pattern_id": pattern_id,
        "family": family,
        "error_code": code,
        "applies_to": [case["product_code"]] if case.get("product_code") else [],
        "text": describe(
            family,
            code,
            case.get("summary") or "",
            case.get("cause") or "",
            case.get("action") or "",
        ),
        "source": "live",
    }


def pattern_evidence(
    row: Mapping[str, Any], cases: Sequence[Mapping[str, Any]], score: float
) -> Evidence:
    """패턴 + 그 패턴으로 해결된 사례(대표가 앞) → 초안 근거.

    doc_id 는 대표 사례 (시연 집계 eval_join.live_case_usage 가 사례 id 로 센다).
    """
    example = cases[0]
    live = sum(1 for c in cases if c.get("data_split", "live") == "live")
    count = f"Resolved {len(cases)} time(s)" + (f", {live} in operation" if live else "")
    reply = (example.get("final_reply") or "").strip()[:EXAMPLE_CHARS]
    return Evidence(
        source="cases",
        doc_id=example["case_id"],
        text=f"{row['text']}\n{count}\nExample reply ({example['case_id']}): {reply}",
        score=score,
        metadata={
            "pattern_id": row["pattern_id"],
            "family": row.get("family") or "",
            "error_code": row.get("error_code") or "",
            "applies_to": ";".join(row.get("applies_to") or []),
            "case_count": str(len(cases)),
            # 다른 제품 · 다른 유형 사례 순서(finalize_evidence)는 패턴에 쓰지 않는다
            "product_code": "",
            "category": "",
        },
    )


# 검색기 ---------------------------------------------------------------------------------------


class PgPatternRetriever:
    """pgvector: 문의 임베딩 ↔ 해결된 적 있는 패턴 설명. score = 1 - 코사인 거리."""

    calibrated = False  # 문의 전환 기준값과 상관없다 (사례는 근거 본보기)

    _PATTERNS = """
        WITH learned AS (
            SELECT pattern_id FROM resolution_cases
            WHERE active AND pattern_id IS NOT NULL GROUP BY pattern_id
        )
        SELECT p.pattern_id, p.family, p.error_code, p.applies_to, p.text,
               p.embedding <=> CAST(:query AS vector) AS distance
        FROM case_patterns AS p JOIN learned USING (pattern_id)
        WHERE p.embedding IS NOT NULL
        ORDER BY distance LIMIT :k
    """
    _CASES = """
        SELECT pattern_id, case_id, final_reply, data_split FROM resolution_cases
        WHERE active AND pattern_id = ANY(CAST(:ids AS text[]))
        ORDER BY pattern_id, (data_split = 'live') DESC, created_at DESC, case_id DESC
    """

    def __init__(
        self, engine: Any = None, embed_fn: Callable[[str], Sequence[float]] | None = None
    ):
        from cs_agent.agents.retrieval import _embed_query

        self.engine = engine
        self.embed_fn = embed_fn or _embed_query

    def search(self, query: str, k: int = 5, where: dict[str, str] | None = None) -> list[Evidence]:
        import sqlalchemy as sa

        from cs_agent.agents.retrieval import _engine

        if where:
            raise ValueError("패턴 검색은 where 를 받지 않는다 (finalize_evidence 가 거른다)")
        vector = str(list(self.embed_fn(query)))
        with (self.engine or _engine()).connect() as conn:
            rows = conn.execute(sa.text(self._PATTERNS), {"query": vector, "k": k}).mappings().all()
            ids = [r["pattern_id"] for r in rows]
            cases: dict[str, list[dict]] = {}
            for c in conn.execute(sa.text(self._CASES), {"ids": ids}).mappings():
                cases.setdefault(c["pattern_id"], []).append(dict(c))
        return [
            pattern_evidence(r, cases[r["pattern_id"]], round(1 - float(r["distance"]), 4))
            for r in rows
            if cases.get(r["pattern_id"])
        ]


class MemoryPatternRetriever:
    """DB · 임베딩이 없는 로컬: train 사례(CSV) + 운영 중 해결 사례(records.live_cases)를 패턴으로
    묶고, 패턴 설명을 키워드로 찾는다. 찾을 때마다 운영 사례를 다시 읽는다 (해결 즉시 반영)."""

    calibrated = False

    def __init__(self, train: Sequence[Mapping[str, Any]], records: Any = None) -> None:
        self.train = list(train)
        self.records = records

    def search(self, query: str, k: int = 5, where: dict[str, str] | None = None) -> list[Evidence]:
        from cs_agent.agents.retrieval import KeywordRetriever

        live = list(self.records.live_cases()) if self.records is not None else []
        grouped: dict[str, list[Mapping[str, Any]]] = {}
        rows: dict[str, dict] = {}
        for case in [*reversed(live), *self.train]:  # 운영 사례(최근)가 대표
            row = pattern_row(case)
            if row is None:
                continue
            rows.setdefault(row["pattern_id"], row)
            grouped.setdefault(row["pattern_id"], []).append(case)
        items = [(pattern_evidence(rows[p], cs, 0.0), rows[p]["text"]) for p, cs in grouped.items()]
        return KeywordRetriever(items).search(query, k, where)


def train_cases(raw_dir: Path | None = None) -> list[dict]:
    """data/raw 해결 사례 중 train 티켓에 연결된 것 (valid · test 사례는 학습 대상이 아니다)."""
    from cs_agent.agents.retrieval import _read_csv
    from cs_agent.config import get_settings

    raw_dir = raw_dir or get_settings().raw_data_dir
    tickets = {t["ticket_id"]: t for t in _read_csv(raw_dir / "tickets.csv")}
    cases = []
    for case in _read_csv(raw_dir / "resolution_cases.csv"):
        ticket = tickets.get(case["ticket_id"])
        if not ticket or ticket["data_split"] != "train":
            continue
        cases.append(
            {
                "case_id": case["case_id"],
                "pattern_id": case.get("fault_id") or None,
                "product_family": case["product_family"],
                "product_code": case["product_code"],
                "error_code": case.get("error_code") or None,
                "summary": case.get("case_summary") or case.get("symptom") or "",
                "cause": case.get("root_cause") or "",
                "action": case.get("action_taken") or "",
                "final_reply": ticket.get("final_reply", ""),
                "data_split": "train",
            }
        )
    return cases


def learned_patterns(cases: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    """pattern_id → 해결 건수 (점검 · 보고용)."""
    counts: dict[str, int] = {}
    for case in cases:
        if (row := pattern_row(case)) is not None:
            counts[row["pattern_id"]] = counts.get(row["pattern_id"], 0) + 1
    return counts
