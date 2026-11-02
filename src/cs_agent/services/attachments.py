# 문의 첨부 파일 저장소 (담당 김동규) — 고객이 문의서에 붙인 사진·문서를 문의번호별로 디스크에 둔다
#
# api/inquiries.py 가 쓴다. 고객 화면은 문의를 낸 뒤 파일을 하나씩 올리고(POST),
# 내 문의 · 상담원 화면은 목록(GET)과 파일(GET …/{attachment_id})을 받아 보여 준다.
#
# 정해 둔 것
# - 위치: settings.attachments_dir/<ticket_id>/<attachment_id>.bin + 같은 이름 .json(이름·형식·크기)
#   docker compose 에서는 attachments 볼륨이라 컨테이너를 다시 만들어도 남는다.
# - 크기: 한 파일 8MB(nginx client_max_body_size 10m 안),
#   한 문의 20개(InquiryIn.attachment_names 와 같다)
# - 이름은 화면에 보일 이름일 뿐이다. 디스크 경로는 서버가 만든 id 로만 만든다 (경로 조작 방지).
# - 그림 중 브라우저가 바로 그려도 안전한 형식(INLINE_TYPES)만 화면 안에서 연다. SVG·HTML 등은
#   스크립트를 품을 수 있어 내려받기로만 준다 (api/inquiries.py).
import json
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel

MAX_BYTES = 8 * 1024 * 1024
MAX_FILES = 20
INLINE_TYPES = frozenset({"image/png", "image/jpeg", "image/gif", "image/webp", "image/bmp"})

_TICKET_ID = re.compile(r"^T-[0-9A-F]{12}$")
_ATTACHMENT_ID = re.compile(r"^[0-9a-f]{32}$")
_CONTENT_TYPE = re.compile(r"^[\w.+-]+/[\w.+-]+$")


class AttachmentError(ValueError):
    """올릴 수 없는 파일 (빈 파일 · 너무 큼 · 개수 초과)."""


class Attachment(BaseModel):
    attachment_id: str
    name: str
    content_type: str
    size: int
    uploaded_at: datetime


class AttachmentStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    def _dir(self, ticket_id: str) -> Path:
        if not _TICKET_ID.match(ticket_id):
            raise KeyError(ticket_id)
        return self.root / ticket_id

    def save(self, ticket_id: str, name: str, content_type: str, data: bytes) -> Attachment:
        if not data:
            raise AttachmentError("빈 파일은 올릴 수 없어요")
        if len(data) > MAX_BYTES:
            raise AttachmentError(f"파일은 {MAX_BYTES // (1024 * 1024)}MB 까지 올릴 수 있어요")
        if len(self.list(ticket_id)) >= MAX_FILES:
            raise AttachmentError(f"한 문의에 파일은 {MAX_FILES}개까지예요")
        content_type = content_type.split(";", 1)[0].strip().lower()
        meta = Attachment(
            attachment_id=uuid.uuid4().hex,
            name=Path(name.replace("\\", "/")).name.strip()[:200] or "file",
            content_type=content_type
            if _CONTENT_TYPE.match(content_type)
            else "application/octet-stream",
            size=len(data),
            uploaded_at=datetime.now(UTC),
        )
        folder = self._dir(ticket_id)
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"{meta.attachment_id}.bin").write_bytes(data)
        (folder / f"{meta.attachment_id}.json").write_text(meta.model_dump_json(), encoding="utf-8")
        return meta

    def list(self, ticket_id: str) -> list[Attachment]:
        folder = self._dir(ticket_id)
        if not folder.is_dir():
            return []
        rows = [_read(p) for p in folder.glob("*.json")]
        return sorted(rows, key=lambda a: a.uploaded_at)

    def open(self, ticket_id: str, attachment_id: str) -> tuple[Attachment, Path]:
        """(정보, 파일 경로). 없으면 KeyError."""
        if not _ATTACHMENT_ID.match(attachment_id):
            raise KeyError(attachment_id)
        folder = self._dir(ticket_id)
        meta_path, data_path = folder / f"{attachment_id}.json", folder / f"{attachment_id}.bin"
        if not (meta_path.is_file() and data_path.is_file()):
            raise KeyError(attachment_id)
        return _read(meta_path), data_path


def _read(meta_path: Path) -> Attachment:
    return Attachment(**json.loads(meta_path.read_text(encoding="utf-8")))
