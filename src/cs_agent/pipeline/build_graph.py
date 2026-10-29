# 사례 학습 지식 그래프 적재 (CSA-70 · 김동규) — 설계안: https://claude.ai/artifact/NhXpbnwscYFvyCW2PzoaeB
#
# 기준표 3개(product_master · fault_catalog · firmware_history)와 해결 사례(resolution_cases),
# 패턴 설명 임베딩(case_patterns)을 Neo4j 에 MERGE 로 넣는다. 여러 번 돌려도 같은 결과다:
# 노드는 id 로 MERGE, 이번에 쓴 노드의 나가는 관계는 지우고 다시 만든다.
#
# 실행 순서 (README): prepare_data → embed_docs --target all → build_graph (한 번)
#   uv run --extra graph python -m cs_agent.pipeline.build_graph
#   --dry-run: Neo4j 에 쓰지 않고 노드·관계 수만 / --embed-missing: 벡터 없는 고장 설명을 임베딩
#
# 그래프 (모든 노드의 키는 id)
#   Family(제품군) · Product(제품 코드) · Fault(fault_id / LIVE-…) · ErrorCode(코드) · Part(부품명)
#   Firmware("제품@버전") · DocSection("doc_id#절", 사례 cited 와 같은 모양) · Case(case_id)
#   (Product)-[:IN_FAMILY]->(Family)        (Fault)-[:APPLIES_TO]->(Product)
#   (Fault)-[:SHOWS_CODE]->(ErrorCode)      (Fault)-[:NEEDS_PART]->(Part)
#   (Fault)-[:FIXED_IN]->(Firmware)         (Fault)-[:EXPLAINED_IN]->(DocSection)  ← 사례 cited
#   (Case)-[:INSTANCE_OF]->(Fault)          (Case)-[:ON_PRODUCT]->(Product)
#   (Case)-[:CITED]->(DocSection)
#   Fault.embedding = 패턴 설명 임베딩 (case_patterns, 1536차원) + 벡터 인덱스 fault_embedding.
#   Fault.case_count = active 사례 수 (재문의로 다시 열린 사례는 빠진다).
#
# 정해 둔 것
# - 사례는 DB(resolution_cases: train + 운영 해결 사례)에서 읽는다. DB 가 비었거나 없으면
#   data/raw 의 train 사례(568건)로 대신한다 (로컬 시연용, 운영 사례·임베딩 없음).
# - 문서 절은 data/raw/docs 를 pipeline/chunking.py 로 자른 절이다 (doc_chunks 와 같은 원천).
# - FIXED_IN 은 firmware_history 에 있는 버전만 잇는다 (없는 버전 노드를 만들지 않는다).
import argparse
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cs_agent.config import get_settings

NODE_LABELS = ("Family", "Product", "Fault", "ErrorCode", "Part", "Firmware", "DocSection", "Case")
# 관계 → (시작 노드, 끝 노드)
RELATIONS: dict[str, tuple[str, str]] = {
    "IN_FAMILY": ("Product", "Family"),
    "APPLIES_TO": ("Fault", "Product"),
    "SHOWS_CODE": ("Fault", "ErrorCode"),
    "NEEDS_PART": ("Fault", "Part"),
    "FIXED_IN": ("Fault", "Firmware"),
    "EXPLAINED_IN": ("Fault", "DocSection"),
    "INSTANCE_OF": ("Case", "Fault"),
    "ON_PRODUCT": ("Case", "Product"),
    "CITED": ("Case", "DocSection"),
}
VECTOR_INDEX = "fault_embedding"
BATCH = 500

Row = dict[str, Any]


@dataclass
class GraphData:
    nodes: dict[str, list[Row]] = field(default_factory=lambda: {k: [] for k in NODE_LABELS})
    rels: dict[str, list[tuple[str, str]]] = field(
        default_factory=lambda: {k: [] for k in RELATIONS}
    )

    def counts(self) -> dict[str, int]:
        return {k: len(v) for k, v in self.nodes.items()} | {
            k: len(v) for k, v in self.rels.items()
        }


def _s(value: Any) -> str:
    text = str(value).strip() if value is not None else ""
    return "" if text.lower() == "nan" else text


def _yes(value: Any) -> bool:
    return _s(value).upper() in ("Y", "YES", "TRUE", "1")


def section_id(doc_id: str, section: str | None) -> str:
    return f"{doc_id}#{section}" if section else doc_id


def firmware_id(product_code: str, version: str) -> str:
    return f"{product_code}@{version}"


def fault_node(pattern: Mapping[str, Any], catalog: Mapping[str, Any] | None = None) -> Row:
    """고장 노드. 카탈로그 행이 있으면 증상·원인·진단·조치·심각도·출동·RMA 를 싣는다."""
    catalog = catalog or {}
    return {
        "id": pattern["pattern_id"],
        "family": pattern.get("family") or "",
        "error_code": pattern.get("error_code") or None,
        "applies_to": list(pattern.get("applies_to") or []),
        "text": pattern["text"],  # 패턴 설명 = 임베딩한 글 (case_patterns.describe)
        "source": pattern.get("source") or "catalog",
        "symptom": _s(catalog.get("symptom")),
        "cause": _s(catalog.get("root_cause")),
        "diagnosis": _s(catalog.get("diagnosis")),
        "action": _s(catalog.get("action")),
        "severity": _s(catalog.get("severity_hint")),
        "needs_onsite": _yes(catalog.get("needs_onsite")),
        "needs_rma": _yes(catalog.get("needs_rma")),
        "embedding": pattern.get("embedding"),
    }


def case_node(case: Mapping[str, Any]) -> Row:
    """사례 노드 (build_case · resolution_cases 행 모양)."""
    created = case.get("created_at")
    return {
        "id": case["case_id"],
        "ticket_id": case.get("ticket_id") or "",
        "product_code": case.get("product_code") or "",
        "family": case.get("product_family") or "",
        "category": case.get("category") or "",
        "error_code": case.get("error_code") or "",
        "summary": case.get("summary") or "",
        "cause": case.get("cause") or "",
        "action": case.get("action") or "",
        "final_reply": case.get("final_reply") or "",
        "active": bool(case.get("active", True)),
        "split": case.get("data_split") or "live",
        # 대표 사례 순서 (운영 사례 → 최근 해결). ISO 문자열이라 글자 순서 = 시간 순서
        "resolved_at": created.isoformat() if hasattr(created, "isoformat") else _s(created),
    }


def graph_data(
    products: Iterable[Mapping[str, Any]],
    faults: Iterable[Mapping[str, Any]],
    firmware: Iterable[Mapping[str, Any]],
    cases: Iterable[Mapping[str, Any]],
    patterns: Mapping[str, Mapping[str, Any]],
    sections: Iterable[Mapping[str, Any]],
) -> GraphData:
    """원천 행 → 노드·관계. patterns 는 case_patterns 행(pattern_id → 행, 임베딩 포함)."""
    from cs_agent.agents.case_patterns import catalog_pattern, pattern_row

    data = GraphData()
    nodes: dict[str, dict[str, Row]] = {label: {} for label in NODE_LABELS}
    rels: dict[str, set[tuple[str, str]]] = {rel: set() for rel in RELATIONS}

    def add(label: str, row: Row) -> None:
        nodes[label].setdefault(row["id"], row)

    for p in products:
        add("Family", {"id": p["family"], "name": _s(p.get("family_name"))})
        add(
            "Product",
            {"id": p["product_code"], "name": _s(p.get("product_name")), "family": p["family"]},
        )
        rels["IN_FAMILY"].add((p["product_code"], p["family"]))

    firmware_ids = set()
    for fw in firmware:
        fid = firmware_id(fw["product_code"], fw["fw_version"])
        firmware_ids.add(fid)
        add(
            "Firmware",
            {
                "id": fid,
                "product_code": fw["product_code"],
                "version": fw["fw_version"],
                "release_date": _s(fw.get("release_date")),
                "latest": _yes(fw.get("is_latest")),
                "changes": _s(fw.get("changes")),
                "doc_id": _s(fw.get("doc_id")),
            },
        )

    for s in sections:
        add("DocSection", dict(s))

    def link_fault(row: Row) -> None:
        for product in row["applies_to"]:
            rels["APPLIES_TO"].add((row["id"], product))
        if row["error_code"]:
            add("ErrorCode", {"id": row["error_code"]})
            rels["SHOWS_CODE"].add((row["id"], row["error_code"]))

    for fault in faults:
        pattern = catalog_pattern(fault)
        stored = patterns.get(pattern["pattern_id"]) or {}
        row = fault_node({**pattern, "embedding": stored.get("embedding")}, fault)
        add("Fault", row)
        link_fault(row)
        if part := _s(fault.get("replacement_part")):
            add("Part", {"id": part})
            rels["NEEDS_PART"].add((row["id"], part))
        if version := _s(fault.get("fw_fix_version")):
            for product in row["applies_to"]:
                if firmware_id(product, version) in firmware_ids:
                    rels["FIXED_IN"].add((row["id"], firmware_id(product, version)))

    for case in cases:
        pattern = pattern_row(case)
        node = case_node(case)
        add("Case", node)
        if pattern is not None:
            if pattern["pattern_id"] not in nodes["Fault"]:  # 카탈로그에 없던 원인 (LIVE-…)
                stored = patterns.get(pattern["pattern_id"]) or pattern
                row = fault_node({**pattern, **stored})
                add("Fault", row)
                link_fault(row)
            rels["INSTANCE_OF"].add((node["id"], pattern["pattern_id"]))
        if node["product_code"]:
            rels["ON_PRODUCT"].add((node["id"], node["product_code"]))
        for cited in case.get("cited") or []:
            rels["CITED"].add((node["id"], cited))
            if pattern is not None:
                rels["EXPLAINED_IN"].add((pattern["pattern_id"], cited))

    for label, rows in nodes.items():
        data.nodes[label] = sorted(rows.values(), key=lambda r: r["id"])
    for rel, pairs in rels.items():
        start, end = RELATIONS[rel]
        # 끝 노드가 없는 관계는 버린다 (문서에 없는 절, 기준표에 없는 제품)
        data.rels[rel] = sorted((a, b) for a, b in pairs if a in nodes[start] and b in nodes[end])
    return data


# 원천 읽기 ------------------------------------------------------------------------------------


def doc_sections(chunks: Iterable[Any] | None = None) -> list[Row]:
    """문서 절 (긴 절을 나눈 조각은 한 절로)."""
    if chunks is None:
        from cs_agent.pipeline.chunking import iter_doc_chunks

        chunks = iter_doc_chunks()
    sections: dict[str, Row] = {}
    for chunk in chunks:
        sid = section_id(chunk.doc_id, chunk.section)
        sections.setdefault(
            sid,
            {
                "id": sid,
                "doc_id": chunk.doc_id,
                "section": chunk.section,
                "title": chunk.title,
                "doc_type": chunk.metadata.get("doc_type", ""),
            },
        )
    return list(sections.values())


def csv_cases(raw_dir: Path | None = None) -> list[Row]:
    """DB 가 없을 때: data/raw 의 train 사례 (resolution_cases 적재와 같은 모양)."""
    from cs_agent.agents.case_patterns import train_cases
    from cs_agent.agents.retrieval import _read_csv

    raw_dir = raw_dir or get_settings().raw_data_dir
    refs = {
        r["case_id"]: section_id(r["reference_doc_id"], r.get("reference_section"))
        for r in _read_csv(raw_dir / "resolution_cases.csv")
        if r.get("reference_doc_id")
    }
    return [
        {**c, "cited": [refs[c["case_id"]]] if c["case_id"] in refs else [], "active": True}
        for c in train_cases(raw_dir)
    ]


def db_inputs(engine: Any) -> tuple[list[Row], dict[str, Row]]:
    """resolution_cases 전체(train + 운영) · case_patterns (임베딩 포함)."""
    import sqlalchemy as sa

    from cs_agent.db.models import CasePattern, ResolutionCase

    columns = (
        "case_id ticket_id summary category product_code product_family error_code cause "
        "action final_reply cited active data_split pattern_id created_at"
    ).split()
    with engine.connect() as conn:
        cases = [
            dict(r)
            for r in conn.execute(
                sa.select(*(getattr(ResolutionCase, c) for c in columns)).order_by(
                    ResolutionCase.case_id
                )
            ).mappings()
        ]
        patterns = {
            r["pattern_id"]: {
                **r,
                "embedding": [float(x) for x in r["embedding"]]
                if r["embedding"] is not None
                else None,
            }
            for r in conn.execute(
                sa.select(
                    CasePattern.pattern_id,
                    CasePattern.family,
                    CasePattern.error_code,
                    CasePattern.applies_to,
                    CasePattern.text,
                    CasePattern.source,
                    CasePattern.embedding,
                )
            ).mappings()
        }
    return cases, patterns


def load_inputs(engine: Any = None) -> tuple[list[Row], dict[str, Row], str]:
    """(사례, 패턴, 출처). DB 에 사례가 없으면 CSV train 사례 · 임베딩 없음."""
    import sqlalchemy as sa

    try:
        engine = engine or sa.create_engine(get_settings().database_url, pool_pre_ping=True)
        cases, patterns = db_inputs(engine)
    except Exception as e:  # DB 가 없거나 마이그레이션 전
        print(f"DB 를 읽지 못함 → data/raw train 사례로 적재 ({type(e).__name__})")
        return csv_cases(), {}, "csv"
    if not cases:
        print("resolution_cases 가 비어 있음 → data/raw train 사례로 적재 (embed_docs 먼저 권장)")
        return csv_cases(), patterns, "csv"
    return cases, patterns, "db"


def build(cases: Sequence[Row], patterns: Mapping[str, Row]) -> GraphData:
    from cs_agent.agents.retrieval import _read_csv

    ref = get_settings().ref_dir
    return graph_data(
        _read_csv(ref / "product_master.csv"),
        _read_csv(ref / "fault_catalog.csv"),
        _read_csv(ref / "firmware_history.csv"),
        cases,
        patterns,
        doc_sections(),
    )


def embed_missing(data: GraphData, embed_fn: Callable[[Sequence[str]], list[list[float]]]) -> int:
    """벡터 없는 고장 설명을 임베딩한다 (case_patterns 가 비었을 때 시연용)."""
    pending = [row for row in data.nodes["Fault"] if not row.get("embedding")]
    for row in pending:
        row["embedding"] = embed_fn([row["text"]])[0]
    return len(pending)


# Neo4j 쓰기 -----------------------------------------------------------------------------------


def _batches(rows: Sequence[Any]) -> Iterable[Sequence[Any]]:
    for i in range(0, len(rows), BATCH):
        yield rows[i : i + BATCH]


def ensure_schema(session: Any, dimensions: int) -> None:
    """id 고유 제약 + 고장 설명 벡터 인덱스 (코사인)."""
    for label in NODE_LABELS:
        session.run(
            f"CREATE CONSTRAINT {label.lower()}_id IF NOT EXISTS "
            f"FOR (n:{label}) REQUIRE n.id IS UNIQUE"
        )
    session.run(
        f"CREATE VECTOR INDEX {VECTOR_INDEX} IF NOT EXISTS FOR (f:Fault) ON f.embedding "
        f"OPTIONS {{indexConfig: {{`vector.dimensions`: {int(dimensions)}, "
        "`vector.similarity_function`: 'cosine'}}"
    )


def refresh_case_counts(session: Any, fault_ids: Sequence[str] | None = None) -> None:
    """Fault.case_count = active 사례 수."""
    session.run(
        "MATCH (f:Fault) WHERE $ids IS NULL OR f.id IN $ids "
        "SET f.case_count = COUNT { (:Case {active: true})-[:INSTANCE_OF]->(f) }",
        ids=list(fault_ids) if fault_ids is not None else None,
    )


def write(driver: Any, data: GraphData, dimensions: int) -> None:
    """MERGE 로 넣는다. 이번에 쓴 노드의 나가는 관계는 지우고 다시 만든다 (다시 돌려도 같다)."""
    with driver.session() as session:
        ensure_schema(session, dimensions)
        for label, rows in data.nodes.items():
            for batch in _batches(rows):
                session.run(
                    f"UNWIND $rows AS r MERGE (n:{label} {{id: r.id}}) SET n += r",
                    rows=list(batch),
                )
        for rel, pairs in data.rels.items():
            start, end = RELATIONS[rel]
            starts = [row["id"] for row in data.nodes[start]]
            for batch in _batches(starts):
                session.run(
                    f"UNWIND $ids AS id MATCH (:{start} {{id: id}})-[r:{rel}]->() DELETE r",
                    ids=list(batch),
                )
            for batch in _batches(pairs):
                session.run(
                    f"UNWIND $pairs AS p MATCH (a:{start} {{id: p[0]}}) "
                    f"MATCH (b:{end} {{id: p[1]}}) MERGE (a)-[:{rel}]->(b)",
                    pairs=[list(p) for p in batch],
                )
        refresh_case_counts(session)


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="사례 학습 지식 그래프 적재 (Neo4j)")
    parser.add_argument("--dry-run", action="store_true", help="Neo4j 에 쓰지 않고 수만 센다")
    parser.add_argument(
        "--embed-missing", action="store_true", help="벡터 없는 고장 설명을 임베딩 (live)"
    )
    args = parser.parse_args(argv)

    settings = get_settings()
    cases, patterns, origin = load_inputs()
    data = build(cases, patterns)
    if args.embed_missing:
        from cs_agent.pipeline.embed_docs import embed

        print(f"고장 설명 임베딩 {embed_missing(data, embed)}건")
    with_vector = sum(1 for r in data.nodes["Fault"] if r.get("embedding"))
    print(f"사례 출처={origin} · 고장 벡터 {with_vector}/{len(data.nodes['Fault'])}")
    for name, n in data.counts().items():
        print(f"  {name:<13} {n}")
    if args.dry_run:
        return

    from cs_agent.agents.knowledge_graph import connect

    driver = connect(settings)
    try:
        write(driver, data, settings.embedding_dim)
    finally:
        driver.close()
    print(f"적재 완료: {settings.neo4j_uri}")


if __name__ == "__main__":
    main()
