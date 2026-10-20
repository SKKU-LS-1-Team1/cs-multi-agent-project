from types import SimpleNamespace

import pytest
import sqlalchemy as sa

from cs_agent.config import Settings
from cs_agent.pipeline import embed_docs as pipeline
from cs_agent.pipeline.chunking import Chunk, chunk_markdown
from cs_agent.pipeline.embed_docs import case_rows, case_text, doc_rows, sync_rows


@pytest.fixture(autouse=True)
def embedding_settings(monkeypatch):
    settings = Settings(
        _env_file=None, embedding_dim=2, embedding_model="test-embedding", llm_provider="fake"
    )
    monkeypatch.setattr(pipeline, "get_settings", lambda: settings)
    return settings


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
    # CSA-24 정식 스키마의 열·NOT NULL 제약 (pgvector/JSONB 대신 SQLite JSON).
    engine = sa.create_engine("sqlite://")
    metadata = sa.MetaData()
    sa.Table(
        "doc_chunks",
        metadata,
        sa.Column("id", sa.String, primary_key=True),
        *(sa.Column(c, sa.String) for c in ("doc_id", "section", "title", "doc_type")),
        *(sa.Column(c, sa.String) for c in ("product_code", "family", "text", "text_hash")),
        *(sa.Column(c, sa.String) for c in ("revision", "language")),
        sa.Column("embedding", sa.JSON),
    )
    sa.Table(
        "resolution_cases",
        metadata,
        sa.Column("case_id", sa.String, primary_key=True),
        *(
            sa.Column(c, sa.String)
            for c in (
                "ticket_id",
                "category",
                "product_code",
                "product_family",
                "error_code",
                "resolved_by_dept",
                "review_action",
                "feedback",
                "feedback_reason",
            )
        ),
        *(
            sa.Column(c, sa.Text, nullable=False)
            for c in (
                "text",
                "summary",
                "cause",
                "action",
                "final_reply",
            )
        ),
        sa.Column("cited", sa.JSON, nullable=False),
        *(
            sa.Column(c, sa.Boolean, nullable=False)
            for c in (
                "edited",
                "source_fix_needed",
                "active",
            )
        ),
        sa.Column("data_split", sa.String, nullable=False),
        sa.Column("text_hash", sa.String),
        sa.Column("embedding", sa.JSON),
    )
    metadata.create_all(engine)
    with engine.connect() as connection:
        yield connection


def test_doc_rows_use_chunk_id_and_filter_columns() -> None:
    rows = doc_rows([_chunk("2.1", "| A | B |"), _chunk("2.1", "more", part=2)])

    assert [r["id"] for r in rows] == ["DS-TEST-1#2.1", "DS-TEST-1#2.1:2"]
    assert rows[0]["text"] == (
        "Product: TEST-1\nDocument type: DS\nTest product — Datasheet — 2.1. Ratings\n\n| A | B |"
    )
    assert rows[0]["section"] == rows[1]["section"] == "2.1"
    assert (rows[0]["doc_type"], rows[0]["product_code"], rows[0]["family"]) == (
        "DS",
        "TEST-1",
        "LV_BREAKER",
    )
    assert len(rows[0]["text_hash"]) == 64


def test_doc_rows_preserve_revision_and_language(conn):
    chunk = _chunk("1", "Overview")
    chunk.metadata.update(revision="R2", language="en")
    rows = doc_rows([chunk])
    sync_rows(conn, "doc_chunks", "id", rows, [rows[0]["text"]], embed_fn=CountingEmbed())
    assert conn.execute(sa.text("select revision, language from doc_chunks")).one() == ("R2", "en")


def test_changed_parent_heading_updates_embedding_without_changing_id(conn) -> None:
    doc = """---
doc_id: DS-CONTEXT
title: Datasheet
doc_type: DS
product_code: TEST-1
---
## 2. Technical specifications

### 2.1 Ratings

Rated current: 100 A.
"""
    before = doc_rows(chunk_markdown(doc))
    after = doc_rows(chunk_markdown(doc.replace("Technical specifications", "Electrical ratings")))
    embed = CountingEmbed()

    assert before[0]["id"] == after[0]["id"] == "DS-CONTEXT#2.1"
    assert before[0]["section"] == after[0]["section"] == "2.1"
    assert before[0]["text_hash"] != after[0]["text_hash"]
    for rows in (before, after, after):
        result = sync_rows(
            conn, "doc_chunks", "id", rows, [r["text"] for r in rows], embed_fn=embed
        )

    assert len(embed.calls) == 2
    assert result["embedded"] == 0
    stored = conn.execute(sa.text("select text from doc_chunks")).scalar_one()
    assert "2. Electrical ratings > 2.1. Ratings" in stored


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


def test_metadata_only_revision_updates_without_reembedding(conn):
    chunk = _chunk("1", "Overview")
    chunk.metadata["revision"] = "R1"
    before = doc_rows([chunk])
    embed = CountingEmbed()
    sync_rows(conn, "doc_chunks", "id", before, [before[0]["text"]], embed_fn=embed)
    vector = conn.execute(sa.text("select embedding from doc_chunks")).scalar_one()

    chunk.metadata["revision"] = "R2"
    after = doc_rows([chunk])
    result = sync_rows(conn, "doc_chunks", "id", after, [after[0]["text"]], embed_fn=embed)

    assert result["embedded"] == 0
    assert len(embed.calls) == 1
    assert conn.execute(sa.text("select revision, embedding from doc_chunks")).one() == (
        "R2",
        vector,
    )


@pytest.mark.parametrize("changed_text", [False, True])
def test_case_update_preserves_review_state_and_refreshes_citations(conn, changed_text):
    case = {"case_id": "RC-1", "ticket_id": "T-1", "case_summary": "summary"}
    before = case_rows([case], {"T-1": "reply"})
    embed = CountingEmbed()
    sync_rows(conn, "resolution_cases", "case_id", before, [before[0]["text"]], embed_fn=embed)
    conn.execute(
        sa.text(
            "update resolution_cases set active = false, edited = true, source_fix_needed = true"
        )
    )
    conn.commit()
    case.update(reference_doc_id="TG-PLC", reference_section="3.2")
    if changed_text:
        case["case_summary"] = "revised summary"
    after = case_rows([case], {"T-1": "reply"})
    result = sync_rows(
        conn, "resolution_cases", "case_id", after, [after[0]["text"]], embed_fn=embed
    )

    assert result["embedded"] == int(changed_text)
    assert len(embed.calls) == 1 + int(changed_text)
    table = sa.Table("resolution_cases", sa.MetaData(), autoload_with=conn)
    stored = conn.execute(sa.select(table)).one()
    assert stored.cited == ["TG-PLC#3.2"]
    assert stored.active is False
    assert stored.edited is stored.source_fix_needed is True


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


def test_case_rows_fit_official_schema_and_persist_required_values(conn) -> None:
    rows = case_rows(
        [
            {
                "case_id": "RC-1",
                "ticket_id": "T-1",
                "case_summary": "s",
                "action_taken": "Replace unit",
                "product_family": "PLC",
                "reference_doc_id": "TG-PLC",
                "reference_section": "3.2",
                "resolved_by_dept": "FIELD_SVC",
            }
        ],
        {"T-1": "reply"},
    )

    result = sync_rows(
        conn, "resolution_cases", "case_id", rows, [case_text(rows[0])], embed_fn=CountingEmbed()
    )

    assert result["embedded"] == 1
    table = sa.Table("resolution_cases", sa.MetaData(), autoload_with=conn)
    assert set(rows[0]).issubset(table.c.keys())
    row = conn.execute(sa.select(table)).one()
    assert (row.case_id, row.final_reply, row.data_split) == ("RC-1", "reply", "train")
    assert row.action == "Replace unit"
    assert row.text == case_text(rows[0])
    assert row.product_family == "PLC"
    assert row.cited == ["TG-PLC#3.2"]
    assert row.resolved_by_dept == "FIELD_SVC"
    assert row.active is True
    assert row.edited is row.source_fix_needed is False
    assert row.review_action is row.feedback is row.feedback_reason is None

    again = sync_rows(
        conn, "resolution_cases", "case_id", rows, [rows[0]["text"]], embed_fn=CountingEmbed()
    )
    assert again["skipped"] == 1


@pytest.mark.parametrize(
    "reference",
    [
        {},
        {"reference_doc_id": "TG-PLC"},
        {"reference_section": "3.2"},
    ],
)
def test_case_rows_do_not_invent_missing_citation_parts(reference):
    [row] = case_rows([{"case_id": "RC-1", "ticket_id": "T-1", **reference}], {"T-1": "reply"})
    assert row["cited"] == (["TG-PLC"] if reference.get("reference_doc_id") else [])


@pytest.mark.parametrize("column", ["text", "action", "active", "cited"])
def test_outdated_case_schema_stops_before_embedding(conn, column):
    conn.execute(sa.text(f"alter table resolution_cases drop column {column}"))
    rows = case_rows([{"case_id": "RC-1", "ticket_id": "T-1"}], {"T-1": "reply"})
    embed = CountingEmbed()
    with pytest.raises(RuntimeError, match="필수 열"):
        sync_rows(conn, "resolution_cases", "case_id", rows, [rows[0]["text"]], embed_fn=embed)
    assert not embed.calls


def test_sync_rows_requires_table(conn) -> None:
    conn.execute(sa.text("drop table doc_chunks"))

    with pytest.raises(RuntimeError, match="CSA-24"):
        sync_rows(conn, "doc_chunks", "id", [], [], embed_fn=CountingEmbed())


def test_model_change_reembeds_unchanged_text(conn, embedding_settings):
    rows = doc_rows([_chunk("1", "Overview")])
    texts = [r["text"] for r in rows]
    embed = CountingEmbed()
    sync_rows(conn, "doc_chunks", "id", rows, texts, embed_fn=embed)
    embedding_settings.embedding_model = "different-model"
    result = sync_rows(conn, "doc_chunks", "id", rows, texts, embed_fn=embed)

    assert result["embedded"] == 1
    assert len(embed.calls) == 2


def test_dimension_change_reembeds_unchanged_text(conn, embedding_settings):
    rows = doc_rows([_chunk("1", "Overview")])
    texts = [rows[0]["text"]]
    sync_rows(conn, "doc_chunks", "id", rows, texts, embed_fn=CountingEmbed())
    embedding_settings.embedding_dim = 3
    result = sync_rows(conn, "doc_chunks", "id", rows, texts, embed_fn=lambda texts: [[1, 2, 3]])

    assert result["embedded"] == 1
    assert (
        conn.execute(sa.text("select embedding from doc_chunks")).scalar_one() == "[1.0, 2.0, 3.0]"
    )


def test_missing_storage_column_stops_before_embedding(conn):
    conn.execute(sa.text("alter table doc_chunks drop column text_hash"))
    rows = doc_rows([_chunk("1", "Overview")])
    embed = CountingEmbed()
    with pytest.raises(RuntimeError, match="필수 열"):
        sync_rows(conn, "doc_chunks", "id", rows, [rows[0]["text"]], embed_fn=embed)
    assert not embed.calls


def test_dry_run_does_not_embed_update_or_prune(conn):
    rows = doc_rows([_chunk("1", "Overview"), _chunk("2", "Details")])
    embed = CountingEmbed()
    sync_rows(conn, "doc_chunks", "id", rows, [r["text"] for r in rows], embed_fn=embed)
    revised = doc_rows([_chunk("1", "Revised overview")])
    before = conn.execute(sa.text("select * from doc_chunks order by id")).all()
    result = sync_rows(
        conn,
        "doc_chunks",
        "id",
        revised,
        [revised[0]["text"]],
        embed_fn=embed,
        prune=True,
        dry_run=True,
    )

    assert result == {"rows": 1, "embedded": 0, "skipped": 0, "removed": 0, "pending": 1}
    assert len(embed.calls) == 2
    assert conn.execute(sa.text("select * from doc_chunks order by id")).all() == before


@pytest.mark.parametrize("vector", [[1], [float("nan"), 1], [float("inf"), 1], [1e100, 1], [0, 0]])
def test_invalid_vectors_are_not_persisted(conn, vector):
    rows = doc_rows([_chunk("1", "Overview")])
    with pytest.raises(ValueError):
        sync_rows(
            conn, "doc_chunks", "id", rows, [rows[0]["text"]], embed_fn=lambda texts: [vector]
        )
    assert conn.execute(sa.text("select count(*) from doc_chunks")).scalar_one() == 0


def test_mismatched_rows_and_inputs_stop_before_embedding(conn):
    embed = CountingEmbed()
    with pytest.raises(ValueError, match="입력 수"):
        sync_rows(conn, "doc_chunks", "id", doc_rows([_chunk("1", "Overview")]), [], embed_fn=embed)
    assert not embed.calls


def test_empty_prune_is_rejected_without_deleting_rows(conn):
    rows = doc_rows([_chunk("1", "Overview")])
    sync_rows(conn, "doc_chunks", "id", rows, [rows[0]["text"]], embed_fn=CountingEmbed())
    with pytest.raises(ValueError, match="전체 문서"):
        sync_rows(conn, "doc_chunks", "id", [], [], embed_fn=CountingEmbed(), prune=True)
    assert conn.execute(sa.text("select count(*) from doc_chunks")).scalar_one() == 1


def test_failure_rolls_back_only_uncommitted_batch_and_can_resume(conn, monkeypatch):
    monkeypatch.setattr(pipeline, "COMMIT_EVERY", 1)
    rows = doc_rows([_chunk("1", "Overview"), _chunk("2", "Details")])
    texts = [r["text"] for r in rows]
    count = 0

    def flaky_embed(texts):
        nonlocal count
        count += 1
        if count == 2:
            raise TimeoutError("provider unavailable")
        return [[1.0, 2.0]]

    with pytest.raises(TimeoutError):
        sync_rows(conn, "doc_chunks", "id", rows, texts, embed_fn=flaky_embed)
    assert conn.execute(sa.text("select id from doc_chunks")).scalars().all() == [rows[0]["id"]]
    result = sync_rows(conn, "doc_chunks", "id", rows, texts, embed_fn=CountingEmbed())
    assert result["skipped"] == result["embedded"] == 1


def test_fake_provider_never_calls_embedding_api(monkeypatch):
    def unexpected_client():
        pytest.fail("fake 환경에서 실제 클라이언트를 만들면 안 됩니다")

    monkeypatch.setattr(pipeline, "_client", unexpected_client)
    assert pipeline.embed([]) == []
    with pytest.raises(RuntimeError, match="LLM_PROVIDER=live"):
        pipeline.embed(["document"])


def test_actual_embedding_adapter_validates_dimensions_and_retries(monkeypatch, embedding_settings):
    genai = pytest.importorskip("google.genai")
    embedding_settings.llm_provider = "live"
    calls, waits = [], []

    def embed_content(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            raise genai.errors.ServerError(504, {"error": {"message": "timeout"}})
        return SimpleNamespace(embeddings=[SimpleNamespace(values=[1.0, 2.0])])

    monkeypatch.setattr(
        pipeline,
        "_client",
        lambda: SimpleNamespace(models=SimpleNamespace(embed_content=embed_content)),
    )
    monkeypatch.setattr(pipeline.time, "sleep", waits.append)
    assert pipeline.embed(["first", "second"]) == [[1.0, 2.0], [1.0, 2.0]]
    assert [c["contents"] for c in calls] == ["first", "first", "second"]
    assert all(c["config"].output_dimensionality == 2 for c in calls)
    assert waits == [5]


def test_missing_vector_extension_stops_before_reflection(monkeypatch):
    conn = SimpleNamespace(
        dialect=SimpleNamespace(name="postgresql"),
        execute=lambda stmt: SimpleNamespace(scalar_one=lambda: False),
    )
    monkeypatch.setattr(sa, "inspect", lambda conn: SimpleNamespace(has_table=lambda name: True))
    with pytest.raises(RuntimeError, match="vector 확장"):
        pipeline._reflect(conn, "doc_chunks", 2)


def test_postgres_reflection_requires_matching_vector_type(monkeypatch):
    Vector = pytest.importorskip("pgvector.sqlalchemy").Vector
    table = sa.Table(
        "doc_chunks",
        sa.MetaData(),
        *(
            sa.Column(k, sa.String)
            for k in ("id", "doc_id", "section", "title", "text", "text_hash")
        ),
        sa.Column("embedding", Vector(3)),
    )
    conn = SimpleNamespace(
        dialect=SimpleNamespace(name="postgresql"),
        execute=lambda stmt: SimpleNamespace(scalar_one=lambda: True),
    )
    monkeypatch.setattr(sa, "inspect", lambda conn: SimpleNamespace(has_table=lambda name: True))
    monkeypatch.setattr(sa, "Table", lambda *args, **kwargs: table)
    with pytest.raises(RuntimeError, match=r"vector\(2\)"):
        pipeline._reflect(conn, "doc_chunks", 2)
    assert pipeline._reflect(conn, "doc_chunks", 3) is table


def test_cases_not_linked_to_train_are_rejected():
    with pytest.raises(ValueError, match="train"):
        case_rows([{"case_id": "RC-1", "ticket_id": "TEST-TICKET"}], {"TRAIN-TICKET": "reply"})
    with pytest.raises(ValueError, match="train"):
        case_rows([{"case_id": "RC-1", "ticket_id": "T-1", "data_split": "test"}], {"T-1": "reply"})


def test_docs_only_dry_run_does_not_load_cases_or_call_api(conn, monkeypatch, embedding_settings):
    monkeypatch.setattr(pipeline, "iter_doc_chunks", lambda: iter([_chunk("1", "Overview")]))

    def unexpected_cases():
        pytest.fail("문서만 실행할 때 사례 파일을 읽으면 안 됩니다")

    monkeypatch.setattr(pipeline, "load_case_inputs", unexpected_cases)
    monkeypatch.setattr(
        sa,
        "create_engine",
        lambda *args, **kwargs: SimpleNamespace(connect=lambda: conn, dispose=lambda: None),
    )
    pipeline.main(["--target", "docs", "--dry-run"])
    assert conn.closed


def test_missing_case_files_report_prepare_data_step(tmp_path):
    with pytest.raises(RuntimeError, match="CSA-17"):
        pipeline.load_case_inputs(tmp_path)
