# 기술문서 절 단위 나누기 (CSA-18 · 담당 박종석 · Sprint 1)
#
# 입력: data/raw/docs/**/*.md (제품 23개 × DS·IG·TG·RN/MG + FAQ 5개, doc_index.csv 참고)
# 각 문서 앞에 front matter(--- doc_id, doc_type, product_code, family, revision, language ---)가
#   있다.
#
# 할 일
# 1. parse_front_matter(raw) → (메타데이터 dict, 본문)
# 2. chunk_markdown(raw) → Chunk 목록. "## 2. ..." / "### 2.1 ..." 제목마다 자르고 절
#      번호("2.1")를 section 에 넣는다.
#    첫 ## 제목 앞(문서 제목, "SYNTHETIC DATA" 안내문)은 버린다.
#    Chunk = doc_id, section, title, text, metadata
# 3. iter_doc_chunks(docs_dir) → 폴더 전체
# 절 단위여야 tickets 의 reference_section 정답과 비교할 수 있다 (K3).
# 표(| 항목 | 값 |)가 잘리지 않게 한다. 너무 긴 절은 나누되 section 은 유지.
#
# 정해 둔 것
# - FAQ 는 "## Q1. ..." 형식이라 section 은 "Q1".
# - 본문 없이 바로 하위 절로 넘어가는 제목("## 2. Technical specifications" 다음 "### 2.1")은
#   청크를 만들지 않는다. tickets 정답이 이런 제목을 가리키는 건은 없다.
# - 긴 절을 나눈 조각은 part 1, 2, ... 로 구분한다. id 는 첫 조각이 "doc_id#section",
#   다음부터 "doc_id#section:2" (embed_docs 의 upsert id 가 겹치지 않게).
import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

MAX_CHUNK_CHARS = 1500  # 지금 문서의 가장 긴 절은 약 1,100자

_HEADING = re.compile(r"^#{2,3}\s+(Q?\d+(?:\.\d+)*)\.?\s+(.+?)\s*$", re.M)


@dataclass(frozen=True)
class Chunk:
    doc_id: str
    section: str
    title: str
    text: str
    metadata: dict[str, str] = field(default_factory=dict)
    part: int = 1

    @property
    def id(self) -> str:
        base = f"{self.doc_id}#{self.section}"
        return base if self.part == 1 else f"{base}:{self.part}"


def parse_front_matter(raw: str) -> tuple[dict[str, str], str]:
    """'---' 로 둘러싼 front matter → (메타데이터 dict, 본문). 없으면 ({}, raw)."""
    lines = raw.lstrip("﻿").splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return {}, raw
    for end in range(1, len(lines)):
        if lines[end].strip() == "---":
            break
    else:
        return {}, raw

    metadata: dict[str, str] = {}
    for line in lines[1:end]:
        key, sep, value = line.partition(":")
        if sep:
            metadata[key.strip()] = value.strip().strip('"').strip("'")
    return metadata, "".join(lines[end + 1 :])


def _blocks(text: str) -> list[str]:
    """빈 줄로 나눈 덩어리. 표는 빈 줄 없이 이어지므로 한 덩어리로 남는다."""
    return [block.strip() for block in re.split(r"\n\s*\n", text) if block.strip()]


def _split_long_block(block: str, max_chars: int) -> list[str]:
    """한 덩어리가 max_chars 를 넘으면 줄 단위로 나눈다. 표는 머리 2줄을 조각마다 반복한다."""
    lines = block.splitlines()
    header: list[str] = []
    if len(lines) > 2 and lines[0].startswith("|") and set(lines[1]) <= set("|-: "):
        header, lines = lines[:2], lines[2:]

    pieces: list[str] = []
    current: list[str] = []
    for line in lines:
        candidate = "\n".join(header + current + [line])
        if current and len(candidate) > max_chars:
            pieces.append("\n".join(header + current))
            current = []
        current.append(line)
    if current:
        pieces.append("\n".join(header + current))
    return pieces


def _split_text(text: str, max_chars: int) -> list[str]:
    """절 본문을 max_chars 안으로 나눈다. 덩어리(문단·표·목록) 경계에서 자른다."""
    if len(text) <= max_chars:
        return [text]

    pieces: list[str] = []
    current = ""
    for block in _blocks(text):
        parts = [block] if len(block) <= max_chars else _split_long_block(block, max_chars)
        for part in parts:
            if current and len(current) + 2 + len(part) > max_chars:
                pieces.append(current)
                current = ""
            current = f"{current}\n\n{part}" if current else part
    if current:
        pieces.append(current)
    return pieces


def chunk_markdown(raw: str, max_chars: int = MAX_CHUNK_CHARS) -> list[Chunk]:
    metadata, body = parse_front_matter(raw)
    doc_id = metadata.get("doc_id", "")
    headings = list(_HEADING.finditer(body))

    chunks: list[Chunk] = []
    for heading, next_heading in zip(headings, headings[1:] + [None], strict=True):
        end = next_heading.start() if next_heading else len(body)
        text = body[heading.end() : end].strip()
        if not text:
            continue
        section, title = heading.group(1), heading.group(2)
        for part, piece in enumerate(_split_text(text, max_chars), start=1):
            chunks.append(Chunk(doc_id, section, title, piece, dict(metadata), part))
    return chunks


def iter_doc_chunks(docs_dir: Path | None = None) -> Iterator[Chunk]:
    """docs_dir 아래 모든 .md 의 청크. 기본값은 settings.raw_data_dir / "docs"."""
    if docs_dir is None:
        from cs_agent.config import get_settings

        docs_dir = get_settings().raw_data_dir / "docs"
    for path in sorted(Path(docs_dir).rglob("*.md")):
        yield from chunk_markdown(path.read_text(encoding="utf-8"))
