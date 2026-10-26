"""해결 사례 패턴 DB (CSA-28): 처리된 문의를 고장 패턴으로 배우고, 패턴 설명으로 찾는다."""

from test_db import db, needs_db  # noqa: F401 — 실제 Postgres fixture (TEST_DATABASE_URL)

from cs_agent.agents.case_patterns import (
    LIVE_PREFIX,
    assign_pattern,
    catalog_rows,
    pattern_evidence,
    pattern_row,
    train_cases,
)
from cs_agent.agents.retrieval import finalize_evidence
from cs_agent.schemas import Extraction

E_OC = "Acceleration time too short for load inertia"  # FLT-001 (DRIVE, E.OC)


def test_catalog_faults_are_the_patterns():
    rows = {r["pattern_id"]: r for r in catalog_rows()}
    assert len(rows) == 97
    flt = rows["FLT-001"]
    assert (flt["family"], flt["error_code"], flt["source"]) == ("DRIVE", "E.OC", "catalog")
    assert "INV-LSLV0075-S100" in flt["applies_to"]
    for part in ("Symptom: Over-current trip during acceleration", f"Cause: {E_OC}", "Action: "):
        assert part in flt["text"]


def test_every_train_case_learns_its_catalog_fault_by_cause():
    """학습 데이터 불변식: 확정 원인 → 고장이 1:1 (그래서 운영 사례도 원인으로 패턴을 정한다)."""
    import csv

    from cs_agent.config import get_settings

    with (get_settings().raw_data_dir / "resolution_cases.csv").open(encoding="utf-8-sig") as f:
        fault = {r["case_id"]: r["fault_id"] for r in csv.DictReader(f)}
    cases = train_cases()
    assert len(cases) == 568
    assert all(
        assign_pattern(c["product_family"], c["cause"]) == fault[c["case_id"]] for c in cases
    )


def test_new_cause_becomes_a_live_pattern():
    pid = assign_pattern("DRIVE", "Loose terminal on the braking resistor")
    assert pid.startswith(f"{LIVE_PREFIX}DRIVE-")
    # 같은 원인(대소문자·문장부호 무시)은 같은 패턴
    assert assign_pattern("DRIVE", "loose terminal, on the BRAKING resistor!") == pid
    assert assign_pattern("DRIVE", E_OC.upper()) == "FLT-001"
    assert assign_pattern(None, "anything").startswith(f"{LIVE_PREFIX}ANY-")
    assert assign_pattern("DRIVE", "  ") is None

    row = pattern_row(
        {
            "product_family": "DRIVE",
            "product_code": "INV-LSLV0075-S100",
            "error_code": "e.ov",
            "summary": "Trips on braking",
            "cause": "Loose terminal on the braking resistor",
            "action": "Retighten to 2.5 N·m",
        }
    )
    assert (row["pattern_id"], row["source"], row["error_code"]) == (pid, "live", "E.OV")
    assert row["applies_to"] == ["INV-LSLV0075-S100"]
    assert "Action: Retighten to 2.5 N·m" in row["text"]


def _pattern(pid: str, score: float, **row):
    base = {"pattern_id": pid, "family": "DRIVE", "error_code": None, "applies_to": [], "text": pid}
    case = {"case_id": f"RC-{pid}", "final_reply": "r", "data_split": "train"}
    return pattern_evidence(base | row, [case], score)


def test_finalize_keeps_patterns_of_the_product_and_error_code():
    candidates = [
        _pattern("OTHER-PRODUCT", 0.9, applies_to=["INV-LSLV0750-iS7"]),
        _pattern("OTHER-CODE", 0.8, error_code="E.OV"),
        _pattern("SAME-CODE", 0.7, error_code="E.OC"),
        _pattern("NO-CODE", 0.6),
        _pattern("OTHER-FAMILY", 0.95, family="PLC"),
    ]
    extraction = Extraction(
        product_code="INV-LSLV0075-S100", product_family="DRIVE", error_code="E.OC"
    )
    final = finalize_evidence(candidates, extraction)
    assert [e.metadata["pattern_id"] for e in final] == ["SAME-CODE", "NO-CODE"]

    # 문의 에러코드를 가진 패턴이 후보에 없으면 에러코드로 거르지 않는다
    final = finalize_evidence(candidates[1:2] + candidates[3:4], extraction)
    assert [e.metadata["pattern_id"] for e in final] == ["OTHER-CODE", "NO-CODE"]


def test_pattern_evidence_points_at_the_representative_case():
    cases = [
        {"case_id": "CASE-T-9", "final_reply": "Raised ACC time.", "data_split": "live"},
        {"case_id": "RC-1", "final_reply": "old", "data_split": "train"},
    ]
    row = next(r for r in catalog_rows() if r["pattern_id"] == "FLT-001")
    e = pattern_evidence(row, cases, 0.81)
    assert (e.source, e.doc_id, e.score) == ("cases", "CASE-T-9", 0.81)
    assert e.metadata["pattern_id"] == "FLT-001" and e.metadata["case_count"] == "2"
    assert "Resolved 2 time(s), 1 in operation" in e.text
    assert "Example reply (CASE-T-9): Raised ACC time." in e.text
    # 패턴 근거는 '같은 유형 먼저'·'같은 제품만' 정렬에 끼지 않는다 (제품은 applies_to 로 거른다)
    assert e.metadata["category"] == "" and e.metadata["product_code"] == ""


@needs_db
def test_pg_pattern_search_finds_learned_patterns_with_live_example_first(db):  # noqa: F811
    from sqlalchemy import text

    from cs_agent.agents.case_patterns import PgPatternRetriever
    from cs_agent.db.models import EMBEDDING_DIM
    from cs_agent.services.records import SqlRecords

    engine, Session = db

    def unit(i: int) -> list[float]:
        return [1.0 if j == i else 0.0 for j in range(EMBEDDING_DIM)]

    vectors = {"FLT-001": unit(0), "FLT-002": unit(1)}
    with engine.begin() as conn:
        for row in catalog_rows():
            if row["pattern_id"] in vectors:
                conn.execute(
                    text(
                        "INSERT INTO case_patterns (pattern_id, family, error_code, applies_to, "
                        "text, source, embedding) VALUES (:p, :f, :e, '[]', :t, 'catalog', :v)"
                    ),
                    {
                        "p": row["pattern_id"],
                        "f": row["family"],
                        "e": row["error_code"],
                        "t": row["text"],
                        "v": str(vectors[row["pattern_id"]]),
                    },
                )
        conn.execute(
            text(
                "INSERT INTO resolution_cases (case_id, text, summary, cause, action, final_reply, "
                "cited, edited, source_fix_needed, active, data_split, pattern_id) VALUES "
                "('RC-1', 't', 's', 'c', 'a', 'seed reply', '[]', false, false, true, 'train', "
                "'FLT-001')"
            )
        )
    records = SqlRecords(Session)
    records.save_case(
        {
            "case_id": "CASE-T-1",
            "ticket_id": "T-1",
            "text": "t",
            "summary": "S100 E.OC",
            "product_family": "DRIVE",
            "cause": E_OC,
            "action": "a",
            "final_reply": "live reply",
            "cited": [],
            "pattern_id": "FLT-001",
        }
    )

    retriever = PgPatternRetriever(engine=engine, embed_fn=lambda q: unit(0))
    hits = retriever.search("inverter trips", 5)
    # FLT-002 는 벡터가 있어도 해결된 적이 없어 나오지 않는다 (배운 패턴만)
    assert [(e.metadata["pattern_id"], e.doc_id) for e in hits] == [("FLT-001", "CASE-T-1")]
    assert hits[0].score == 1.0 and hits[0].metadata["case_count"] == "2"

    records.deactivate_case("T-1")  # 재문의로 다시 열림 → 대표가 train 사례로
    assert [e.doc_id for e in retriever.search("inverter trips", 5)] == ["RC-1"]
