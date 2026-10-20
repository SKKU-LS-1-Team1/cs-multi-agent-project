import csv

from cs_agent.config import get_settings
from cs_agent.pipeline.chunking import chunk_markdown, iter_doc_chunks, parse_front_matter

DOC = """---
doc_id: DS-TEST-1
title: "Test product — Datasheet"
doc_type: DS
product_code: TEST-1
family: LV_BREAKER
---

> SYNTHETIC DATA — 교육용 가상 데이터

# Test product — Datasheet

## 1. Overview

Molded case circuit breaker.

## 2. Technical specifications

### 2.1 Ratings

| Item | Value |
|---|---|
| Rated current (In) | 100 A |

## Q3. What is the warranty period?

18 months.
"""


def test_parse_front_matter() -> None:
    metadata, body = parse_front_matter(DOC)

    assert metadata["doc_id"] == "DS-TEST-1"
    assert metadata["title"] == "Test product — Datasheet"
    assert metadata["product_code"] == "TEST-1"
    assert body.lstrip().startswith("> SYNTHETIC DATA")
    assert parse_front_matter("# no front matter") == ({}, "# no front matter")


def test_chunk_markdown_splits_by_section() -> None:
    chunks = chunk_markdown(DOC)

    # 제목 앞 안내문과 본문 없는 "## 2." 는 청크가 되지 않는다
    assert [(c.section, c.title) for c in chunks] == [
        ("1", "Overview"),
        ("2.1", "Ratings"),
        ("Q3", "What is the warranty period?"),
    ]
    assert chunks[1].id == "DS-TEST-1#2.1"
    assert chunks[1].text.startswith("| Item | Value |")
    assert chunks[1].metadata["family"] == "LV_BREAKER"
    assert chunks[1].section_path == "2. Technical specifications > 2.1. Ratings"
    assert chunks[1].metadata["parent_section"] == "2"
    assert chunks[2].section_path == "Q3. What is the warranty period?"
    assert chunks[2].metadata["parent_section"] == ""
    assert all("SYNTHETIC" not in c.text for c in chunks)


def test_parent_and_siblings_keep_only_their_own_body() -> None:
    doc = """---
doc_id: DS-PATH
---
## 2. Technical specifications

Parent introduction.

### 2.1 Ratings

Rated current: 100 A.

### 2.2 Temperature

Operating temperature: 40 °C.

## 3. Ordering

Order in units of 5.
"""
    parent, ratings, temperature, ordering = chunk_markdown(doc)

    assert parent.text == "Parent introduction."
    assert ratings.text == "Rated current: 100 A."
    assert temperature.text == "Operating temperature: 40 °C."
    assert temperature.section_path == "2. Technical specifications > 2.2. Temperature"
    assert "Ratings" not in temperature.section_path
    assert ordering.section_path == "3. Ordering"
    assert ordering.metadata["parent_section"] == ""
    assert [c.id for c in (parent, ratings, temperature, ordering)] == [
        "DS-PATH#2",
        "DS-PATH#2.1",
        "DS-PATH#2.2",
        "DS-PATH#3",
    ]


def test_embedding_text_retains_heading_without_document_title() -> None:
    [chunk] = chunk_markdown("---\ndoc_id: TG-TEST\n---\n## 3. Checks\n\nInspect terminals.")

    assert chunk.embedding_text == "3. Checks\n\nInspect terminals."
    assert chunk.text == "Inspect terminals."


def test_orphan_subsection_does_not_invent_parent() -> None:
    [chunk] = chunk_markdown("---\ndoc_id: DS-TEST\n---\n### 2.1 Ratings\n\n100 A.")

    assert chunk.section_path == "2.1. Ratings"
    assert chunk.metadata["parent_section"] == ""


def test_embedding_context_does_not_repeat_product_code_in_title() -> None:
    doc = DOC.replace(
        'title: "Test product — Datasheet"', 'title: "Test product (TEST-1) — Datasheet"'
    )
    chunk = chunk_markdown(doc)[1]

    assert chunk.embedding_text.count("TEST-1") == 1
    assert "Document type: DS" in chunk.embedding_text
    assert "Technical specifications > 2.1. Ratings" in chunk.embedding_text
    assert chunk.embedding_text.endswith(chunk.text)


def test_family_faq_does_not_inherit_an_individual_product() -> None:
    doc = """---
doc_id: FAQ-DRIVE
title: Drive FAQ
doc_type: FAQ
product_code:
family: DRIVE
---
## Q1. Which products?

S100 and iS7.
"""
    [chunk] = chunk_markdown(doc)

    assert "Product family: DRIVE" in chunk.embedding_text
    assert "Document type: FAQ" in chunk.embedding_text
    assert "Product:" not in chunk.embedding_text
    assert chunk.metadata["product_code"] == ""


def test_long_section_keeps_section_and_table_header() -> None:
    rows = "\n".join(f"| Item {i} | {'x' * 40} |" for i in range(30))
    doc = (
        "---\ndoc_id: TG-TEST\n---\n## 4. Error codes\n\nIntro.\n\n"
        f"| Code | Action |\n|---|---|\n{rows}\n"
    )

    chunks = chunk_markdown(doc, max_chars=400)

    assert len(chunks) > 1
    assert {c.section for c in chunks} == {"4"}
    assert [c.part for c in chunks] == list(range(1, len(chunks) + 1))
    assert len({c.id for c in chunks}) == len(chunks)
    assert chunks[1].id == "TG-TEST#4:2"
    assert all(len(c.text) <= 400 for c in chunks)
    table_chunks = [c for c in chunks if "| Item" in c.text]
    assert all("| Code | Action |\n|---|---|" in c.text for c in table_chunks)
    assert sum(c.text.count("| Item") for c in chunks) == 30


def test_split_subsection_preserves_heading_path_in_every_part() -> None:
    rows = "\n".join(f"| Rating {i} | 100 A |" for i in range(20))
    doc = (
        "---\ndoc_id: DS-SPLIT\n---\n## 2. Technical specifications\n\n"
        f"### 2.1 Ratings\n\n| Item | Value |\n|---|---|\n{rows}\n"
    )
    chunks = chunk_markdown(doc, max_chars=150)

    assert len(chunks) > 1
    assert all(c.section_path == "2. Technical specifications > 2.1. Ratings" for c in chunks)
    assert all(c.metadata["parent_section"] == "2" for c in chunks)
    assert all(c.section_path in c.embedding_text for c in chunks)
    assert sum(c.text.count("| Rating") for c in chunks) == 20
    # 청크별 메타데이터는 독립적이며 한 조각의 변경이 다른 조각에 전파되지 않는다.
    chunks[0].metadata["parent_section"] = "changed"
    assert chunks[1].metadata["parent_section"] == "2"


def test_real_s100_ratings_keep_product_context_and_original_table() -> None:
    path = get_settings().raw_data_dir / "docs/INV-LSLV0075-S100/DS-INV-LSLV0075-S100.md"
    chunks = chunk_markdown(path.read_text(encoding="utf-8"))
    ratings = next(c for c in chunks if c.section == "2.1")

    assert ratings.id == "DS-INV-LSLV0075-S100#2.1"
    assert ratings.section_path == "2. Technical specifications > 2.1. Ratings"
    assert "INV-LSLV0075-S100" in ratings.embedding_text
    assert "Document type: DS" in ratings.embedding_text
    assert "| Rated output (heavy duty) | 7.5 kW / 16 A |" in ratings.text
    assert "SYNTHETIC DATA" not in ratings.embedding_text
    assert "Performance and characteristics" not in ratings.embedding_text


def test_ticket_reference_sections_exist_in_chunks() -> None:
    chunks = list(iter_doc_chunks())
    sections = {(c.doc_id, c.section) for c in chunks}
    path = get_settings().raw_data_dir / "tickets.csv"
    with path.open(encoding="utf-8-sig", newline="") as f:
        refs = [
            (row["reference_doc_id"], row["reference_section"])
            for row in csv.DictReader(f)
            if row["reference_section"]
        ]

    assert len({c.doc_id for c in chunks}) == 107
    assert len({c.id for c in chunks}) == len(chunks)
    assert refs and all(ref in sections for ref in refs)
