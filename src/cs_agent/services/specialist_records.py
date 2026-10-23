"""CSA-62 storage: immutable requests/replies, durable provenance, per-ticket mutation guard."""

import hashlib
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from copy import deepcopy
from datetime import UTC, datetime
from threading import Lock, RLock

from cs_agent.schemas import SpecialistReplyIn, SpecialistRequestIn


class SpecialistConflict(ValueError):
    pass


def request_data(body: SpecialistRequestIn) -> dict:
    return {**body.model_dump(mode="json"), "created_at": datetime.now(UTC), "reply": None}


def same_request(stored: dict, body: SpecialistRequestIn) -> bool:
    return all(stored[k] == v for k, v in body.model_dump(mode="json").items())


def same_reply(stored: dict, body: SpecialistReplyIn) -> bool:
    return all(stored[k] == v for k, v in body.model_dump(mode="json").items())


class MemorySpecialists:
    def _init_specialists(self) -> None:
        self._specialists: dict[str, list[dict]] = {}
        self._ticket_locks: dict[str, RLock] = {}
        self._specialist_mutex = Lock()

    @contextmanager
    def ticket_locks(self, ticket_ids: list[str]) -> Iterator[None]:
        with ExitStack() as stack:
            for ticket_id in sorted(set(ticket_ids)):
                stack.enter_context(self.ticket_lock(ticket_id))
            yield

    @contextmanager
    def ticket_lock(self, ticket_id: str) -> Iterator[None]:
        with self._specialist_mutex:
            lock = self._ticket_locks.setdefault(ticket_id, RLock())
        if not lock.acquire(blocking=False):
            raise SpecialistConflict("문의가 처리 중입니다. 잠시 후 다시 시도해 주세요")
        try:
            yield
        finally:
            lock.release()

    def specialist_requests(self, ticket_id: str) -> list[dict]:
        with self._specialist_mutex:
            return deepcopy(self._specialists.get(ticket_id, []))

    def add_specialist_request(self, ticket_id: str, body: SpecialistRequestIn) -> None:
        with self._specialist_mutex:
            for tid, requests in self._specialists.items():
                for row in requests:
                    if row["request_id"] == str(body.request_id):
                        if tid == ticket_id and same_request(row, body):
                            return
                        raise SpecialistConflict("이미 사용한 요청 ID입니다")
            self._specialists.setdefault(ticket_id, []).append(request_data(body))

    def add_specialist_reply(
        self, ticket_id: str, request_id: str, body: SpecialistReplyIn
    ) -> None:
        with self._specialist_mutex:
            rows = self._specialists.get(ticket_id, [])
            row = next((r for r in rows if r["request_id"] == request_id), None)
            if row is None:
                raise SpecialistConflict("이 문의의 검토 요청을 찾을 수 없습니다")
            if row["reply"]:
                if same_reply(row["reply"], body):
                    return
                raise SpecialistConflict("이미 회신이 등록된 요청입니다")
            if any(
                r["reply"] and r["reply"]["reply_id"] == str(body.reply_id)
                for requests in self._specialists.values()
                for r in requests
            ):
                raise SpecialistConflict("이미 사용한 회신 ID입니다")
            row["reply"] = {**body.model_dump(mode="json"), "created_at": datetime.now(UTC)}


def _row_dict(row) -> dict:
    return {
        "request_id": row.request_id,
        "to_dept": row.to_dept,
        "text": row.text,
        "requested_by": row.requested_by,
        "channel": row.channel,
        "attachment_names": row.attachment_names,
        "created_at": row.created_at,
        "reply": {
            "reply_id": row.reply_id,
            "text": row.reply_text,
            "author": row.reply_author,
            "created_at": row.replied_at,
        }
        if row.reply_id
        else None,
    }


class SqlSpecialists:
    @contextmanager
    def ticket_lock(self, ticket_id: str) -> Iterator[None]:
        with self.ticket_locks([ticket_id]):
            yield

    @contextmanager
    def ticket_locks(self, ticket_ids: list[str]) -> Iterator[None]:
        """Advisory transaction lock covers graph+record writes across API workers.

        A separate short-lived session holds the lock. Writes/checkpoints use their normal
        transactions so no long-running row lock blocks background read/projection jobs.
        """
        from sqlalchemy import text

        with self.sessionmaker.begin() as session:
            for ticket_id in sorted(set(ticket_ids)):
                key = int.from_bytes(
                    hashlib.sha256(f"cs-ticket:{ticket_id}".encode()).digest()[:8],
                    "big",
                    signed=True,
                )
                if not session.scalar(text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": key}):
                    raise SpecialistConflict("문의가 처리 중입니다. 잠시 후 다시 시도해 주세요")
            yield

    def specialist_requests(self, ticket_id: str) -> list[dict]:
        from sqlalchemy import select

        from cs_agent.db.models import SpecialistRequestRow

        with self.sessionmaker() as session:
            rows = session.scalars(
                select(SpecialistRequestRow)
                .where(SpecialistRequestRow.ticket_id == ticket_id)
                .order_by(SpecialistRequestRow.created_at, SpecialistRequestRow.request_id)
            )
            return [_row_dict(row) for row in rows]

    def add_specialist_request(self, ticket_id: str, body: SpecialistRequestIn) -> None:
        from sqlalchemy.exc import IntegrityError

        from cs_agent.db.models import SpecialistRequestRow

        try:
            with self.sessionmaker.begin() as session:
                row = session.get(SpecialistRequestRow, str(body.request_id))
                if row:
                    if row.ticket_id == ticket_id and same_request(_row_dict(row), body):
                        return
                    raise SpecialistConflict("이미 사용한 요청 ID입니다")
                session.add(
                    SpecialistRequestRow(ticket_id=ticket_id, **body.model_dump(mode="json"))
                )
        except IntegrityError as exc:
            raise SpecialistConflict("이미 사용한 요청 ID이거나 문의가 변경되었습니다") from exc

    def add_specialist_reply(
        self, ticket_id: str, request_id: str, body: SpecialistReplyIn
    ) -> None:
        from sqlalchemy import select
        from sqlalchemy.exc import IntegrityError

        from cs_agent.db.models import SpecialistRequestRow

        try:
            with self.sessionmaker.begin() as session:
                row = session.scalar(
                    select(SpecialistRequestRow)
                    .where(
                        SpecialistRequestRow.request_id == request_id,
                        SpecialistRequestRow.ticket_id == ticket_id,
                    )
                    .with_for_update()
                )
                if row is None:
                    raise SpecialistConflict("이 문의의 검토 요청을 찾을 수 없습니다")
                if row.reply_id:
                    if same_reply(_row_dict(row)["reply"], body):
                        return
                    raise SpecialistConflict("이미 회신이 등록된 요청입니다")
                row.reply_id = str(body.reply_id)
                row.reply_text = body.text
                row.reply_author = body.author
                row.replied_at = datetime.now(UTC)
        except IntegrityError as exc:
            raise SpecialistConflict("이미 사용한 회신 ID입니다") from exc
