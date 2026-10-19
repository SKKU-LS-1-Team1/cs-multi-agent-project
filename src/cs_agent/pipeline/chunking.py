"""기술문서를 절(section) 단위로 나눈다 (CSA-18).

절 단위여야 tickets의 `reference_section` 정답과 비교할 수 있다 (K3).
"""

import re
from dataclasses import dataclass
from pathlib import Path

_HEADING_RE = re.compile(r"^(#{2,3})\s+(?:(\d+(?:\.\d+)*)\.?\s+)?(.+)$")


@dataclass
class Chunk:
    doc_id: str
    section: str | None
    title: str
    text: str
    metadata: dict[str, str]


def parse_front_matter(raw: str) -> tuple[dict[str, str], str]:
    if not raw.startswith("---"):
        return {}, raw
    _, head, body = raw.split("---", 2)
    meta = {}
    for line in head.strip().splitlines():
        key, _, value = line.partition(":")
        meta[key.strip()] = value.strip().strip('"')
    return meta, body


def chunk_markdown(raw: str, fallback_doc_id: str = "") -> list[Chunk]:
    meta, body = parse_front_matter(raw)
    doc_id = meta.get("doc_id", fallback_doc_id)
    chunks: list[Chunk] = []
    section, title, lines = None, "", []

    def flush() -> None:
        text = "\n".join(lines).strip()
        if text and title:  # 첫 ## 제목 앞(문서 제목·안내문)은 버린다
            chunks.append(Chunk(doc_id, section, title, text, dict(meta)))

    for line in body.splitlines():
        m = _HEADING_RE.match(line)
        if m:
            flush()
            section, title, lines = m.group(2), m.group(3), []
        else:
            lines.append(line)
    flush()
    return chunks


def iter_doc_chunks(docs_dir: Path) -> list[Chunk]:
    chunks: list[Chunk] = []
    for path in sorted(docs_dir.rglob("*.md")):
        chunks.extend(chunk_markdown(path.read_text(encoding="utf-8"), path.stem))
    return chunks
