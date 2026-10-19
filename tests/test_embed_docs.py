import pytest
import sqlalchemy as sa

from cs_agent.pipeline.chunking import Chunk
from cs_agent.pipeline.embed_docs import case_rows, case_text, doc_rows, sync_rows


def _chunk(section: str, text: str, part: int = 1) -> Chunk:
    metadata = {
        "doc_id": "DS-TEST-1",
        "title": "Test product — Datasheet",
        "doc_type": "DS",
        "product_code": "TEST-1",
        "family": "LV_BREAKER",
    }
    return Chunk("DS-TEST-1", section, "Ratings", text, metadata, part)


class CountingEmbed:
    """API 대신 쓰는 가짜 임베딩. 몇 번 불렸는지 센다."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def __call__(self, texts: list[str]) -> list[list[float]]:
        self.calls += texts
        return [[float(len(t)), 1.0] for t in texts]


@pytest.fixture
def conn():
    # db/models.py 주석의 열 이름대로 만든 테스트 테이블 (pgvector 대신 JSON)
    engine = sa.create_engine("sqlite://")
    metadata = sa.MetaData()
    sa.Table(
        "doc_chunks",
        metadata,
        sa.Column("id", sa.String, primary_key=True),
        *(sa.Column(c, sa.String) for c in ("doc_id", "section", "title", "doc_type")),
        *(sa.Column(c, sa.String) for c in ("product_code", "family", "text", "text_hash")),
        sa.Column("embedding", sa.JSON),
    )
    sa.Table(
        "resolution_cases",
        metadata,
        sa.Column("case_id", sa.String, primary_key=True),
        *(sa.Column(c, sa.String) for c in ("ticket_id", "category", "summary", "final_reply")),
        sa.Column("data_split", sa.String),
        sa.Column("text_hash", sa.String),
        sa.Column("embedding", sa.JSON),
    )
    metadata.create_all(engine)
    with engine.connect() as connection:
        yield connection


def test_doc_rows_use_chunk_id_and_filter_columns() -> None:
    rows = doc_rows([_chunk("2.1", "| A | B |"), _chunk("2.1", "more", part=2)])

    assert [r["id"] for r in rows] == ["DS-TEST-1#2.1", "DS-TEST-1#2.1:2"]
    assert rows[0]["text"] == "Test product — Datasheet — 2.1. Ratings\n\n| A | B |"
    assert rows[0]["section"] == rows[1]["section"] == "2.1"
    assert (rows[0]["doc_type"], rows[0]["product_code"], rows[0]["family"]) == (
        "DS",
        "TEST-1",
        "LV_BREAKER",
    )
    assert len(rows[0]["text_hash"]) == 64


def test_case_rows_join_final_reply() -> None:
    case = {
        "case_id": "RC-0001",
        "ticket_id": "CSV1-000002",
        "category_code": "INSTALL",
        "error_code": float("nan"),
        "case_summary": "VCB contact wear indicator at limit.",
        "root_cause": "Vacuum interrupter end of life",
        "action_taken": "Replace vacuum interrupter",
    }

    [row] = case_rows([case], {"CSV1-000002": "An engineer is assigned."})

    assert row["data_split"] == "train"
    assert row["error_code"] == ""
    assert case_text(row) == (
        "Summary: VCB contact wear indicator at limit.\n"
        "Root cause: Vacuum interrupter end of life\n"
        "Action: Replace vacuum interrupter\n"
        "Final reply: An engineer is assigned."
    )


def test_sync_rows_skips_unchanged_text_and_prunes_stale(conn) -> None:
    embed = CountingEmbed()
    rows = doc_rows([_chunk("1", "Overview"), _chunk("2.1", "Ratings")])
    texts = [r["text"] for r in rows]

    first = sync_rows(conn, "doc_chunks", "id", rows, texts, embed_fn=embed, prune=True)
    again = sync_rows(conn, "doc_chunks", "id", rows, texts, embed_fn=embed, prune=True)

    assert (first["embedded"], again["embedded"], again["skipped"]) == (2, 0, 2)
    assert len(embed.calls) == 2

    revised = doc_rows([_chunk("2.1", "Ratings rev B")])
    result = sync_rows(
        conn, "doc_chunks", "id", revised, [revised[0]["text"]], embed_fn=embed, prune=True
    )

    assert (result["embedded"], result["removed"]) == (1, 1)
    stored = conn.execute(sa.text("select id, text, embedding from doc_chunks")).all()
    assert [(r.id, r.text.endswith("rev B")) for r in stored] == [("DS-TEST-1#2.1", True)]


def test_sync_rows_ignores_columns_missing_from_table(conn) -> None:
    rows = case_rows(
        [{"case_id": "RC-1", "ticket_id": "T-1", "case_summary": "s"}], {"T-1": "reply"}
    )

    result = sync_rows(
        conn, "resolution_cases", "case_id", rows, [case_text(rows[0])], embed_fn=CountingEmbed()
    )

    assert result["embedded"] == 1
    row = conn.execute(sa.text("select * from resolution_cases")).one()
    assert (row.case_id, row.final_reply, row.data_split) == ("RC-1", "reply", "train")


def test_sync_rows_requires_table(conn) -> None:
    conn.execute(sa.text("drop table doc_chunks"))

    with pytest.raises(RuntimeError, match="CSA-24"):
        sync_rows(conn, "doc_chunks", "id", [], [], embed_fn=CountingEmbed())
