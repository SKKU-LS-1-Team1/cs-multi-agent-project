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
    assert all("SYNTHETIC" not in c.text for c in chunks)


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
