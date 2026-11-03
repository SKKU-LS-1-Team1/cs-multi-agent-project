"""Durable customer-scoped semantic index. No writes to tickets, cases or checkpoints.

Exact pgvector ranking within one customer's rows avoids approximate-index filter recall loss.
The periodic worker also backfills existing inquiries; unchanged chunks reuse their embeddings.
"""

import asyncio
import contextvars
import hashlib
import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from threading import BoundedSemaphore

from sqlalchemy import delete, func, or_, select
from sqlalchemy.dialects.postgresql import insert

from cs_agent.agents.customer_followup import judge
from cs_agent.db.models import EMBEDDING_DIM, Ticket
from cs_agent.db.models import InquiryHistoryChunk as Chunk
from cs_agent.pipeline.embed_docs import _validate_vector as validate_vector

_LOG = logging.getLogger(__name__)
_POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix="customer-followup")
_CAPACITY = BoundedSemaphore(2)


def dump(value):
    return value.model_dump(mode="json") if hasattr(value, "model_dump") else value


def customer_source(value) -> str:
    """Only customer-supplied fields, never inferred extraction or staff annotations."""
    value = dump(value) or {}
    text = f"{value.get('subject', '')}\n{value.get('body', '')}".strip()
    supplied = {key: value[key] for key in ("product_code", "provided_fields") if value.get(key)}
    if supplied:
        text += "\nCustomer form fields:\n" + json.dumps(supplied, ensure_ascii=False)
    return text.strip()


def sources_of(state: dict) -> dict[str, str]:
    inquiry = dump(state.get("inquiry")) or {}
    messages = state.get("customer_messages", [])
    sources = {"inquiry": inquiry.get("subject", "") if messages else customer_source(inquiry)}
    for i, message in enumerate(state.get("customer_messages", [])):
        if text := customer_source(message):
            sources[f"customer:{i}"] = text
    for i, event in enumerate(state.get("processing_history", [])):
        if event.get("kind") == "sent" and event.get("text"):
            sources[f"sent:{i}"] = event["text"]
    if state.get("final_reply") and state["final_reply"] not in sources.values():
        sources["sent:latest"] = state["final_reply"]
    resolution = dump(state.get("resolution"))
    if resolution:
        sources["recorded_outcome"] = json.dumps(resolution, ensure_ascii=False, default=str)
    for i, reply in enumerate(state.get("specialist_replies", [])):
        text = reply.get("text") or reply.get("body")
        if text:
            sources[f"specialist:{i}"] = text
    return {key: text for key, text in sources.items() if text.strip()}


def chunks_of(sources: dict[str, str]) -> dict[str, str]:
    result = {}
    for source, text in sources.items():
        for offset in range(0, len(text), 1650):
            result[f"{source}:{offset}"] = text[offset : offset + 1800]
    return result


class CustomerHistory:
    def __init__(self, sessionmaker, embed, model: str, state_reader, llm):
        self.sessions = sessionmaker
        self.embed = embed
        self.version = f"history-v1:{model}:{EMBEDDING_DIM}"
        self.read_state = state_reader
        self.llm = llm
        self._cursor = None

    def snapshot(self, ticket_id: str):
        with self.sessions() as s:
            row = s.get(Ticket, ticket_id)
            if row is None or not row.customer_id:
                return None
            base = {
                # product_code on Ticket is model extraction, not necessarily customer input.
                "inquiry": {
                    "subject": row.subject,
                    "body": row.body,
                    "provided_fields": row.provided_fields,
                },
                "resolution": row.resolution,
            }
            customer, subject, updated = row.customer_id, row.subject, row.updated_at
        state = self.read_state(ticket_id) or base
        # A snapshot is immutable input; background embedding never modifies the original state.
        return customer, subject, updated, sources_of(state)

    def refresh(self, ticket_id: str) -> bool:
        snapshot = self.snapshot(ticket_id)
        if snapshot is None:
            return False
        customer, subject, updated, sources = snapshot
        chunks = chunks_of(sources)
        if len(chunks) > 256:
            raise ValueError("Inquiry history exceeds indexing budget")
        with self.sessions() as s:
            old = {
                r.source_id: r for r in s.scalars(select(Chunk).where(Chunk.ticket_id == ticket_id))
            }
        rows = []
        for source_id, text in chunks.items():
            # Include title in semantic search, keep evidence text verbatim.
            embedding_text = f"{subject}\n{source_id.split(':')[0]}\n{text}"
            digest = hashlib.sha256(embedding_text.encode()).hexdigest()
            previous = old.get(source_id)
            vector = (
                previous.embedding
                if previous is not None
                and previous.text_hash == digest
                and previous.embedding_version == self.version
                else self.embed([embedding_text])[0]
            )
            vector = validate_vector(vector, EMBEDDING_DIM)
            rows.append(
                dict(
                    ticket_id=ticket_id,
                    source_id=source_id,
                    customer_id=customer,
                    text=text,
                    text_hash=digest,
                    embedding=vector,
                    embedding_version=self.version,
                    indexed_at=updated,
                )
            )
        with self.sessions.begin() as s:
            row = s.get(Ticket, ticket_id, with_for_update=True)
            if row is None or row.updated_at != updated or row.customer_id != customer:
                return False  # Source changed during embedding; retry next cycle.
            for values in rows:
                stmt = insert(Chunk).values(**values)
                s.execute(
                    stmt.on_conflict_do_update(
                        index_elements=[Chunk.ticket_id, Chunk.source_id],
                        set_={
                            k: stmt.excluded[k]
                            for k in values
                            if k not in {"ticket_id", "source_id"}
                        },
                    )
                )
            s.execute(
                delete(Chunk).where(Chunk.ticket_id == ticket_id, Chunk.source_id.not_in(chunks))
            )
        return True

    def refresh_batch(self, limit: int = 5) -> int:
        indexed = (
            select(Chunk.ticket_id, func.min(Chunk.indexed_at).label("stamp"))
            .where(Chunk.embedding_version == self.version)
            .group_by(Chunk.ticket_id)
            .subquery()
        )
        query = (
            select(Ticket.ticket_id)
            .outerjoin(indexed, Ticket.ticket_id == indexed.c.ticket_id)
            .where(
                Ticket.customer_id.is_not(None),
                Ticket.customer_id != "",
                or_(indexed.c.stamp.is_(None), indexed.c.stamp < Ticket.updated_at),
            )
            .order_by(Ticket.ticket_id)
        )
        if self._cursor:
            query = query.where(Ticket.ticket_id > self._cursor)
        with self.sessions() as s:
            ids = list(s.scalars(query.limit(limit)))
        if not ids:
            self._cursor = None
            return 0
        count = 0
        for ticket_id in ids:
            self._cursor = ticket_id  # One bad ticket cannot starve all later tickets.
            try:
                count += self.refresh(ticket_id)
            except Exception as exc:
                _LOG.warning("History indexing failed for %s (%s)", ticket_id, type(exc).__name__)
        return count

    def candidates(self, ticket_id, inquiry, limit=5):
        if not inquiry.customer_id:
            return []
        with self.sessions() as s:
            exists = s.scalar(
                select(Ticket.ticket_id)
                .where(
                    Ticket.customer_id == inquiry.customer_id,
                    Ticket.ticket_id != ticket_id,
                    Ticket.received_at <= inquiry.received_at,
                )
                .limit(1)
            )
        if not exists:
            return []
        text = customer_source(inquiry)
        conditions = (
            Ticket.customer_id == inquiry.customer_id,
            Ticket.ticket_id != ticket_id,
            Ticket.received_at <= inquiry.received_at,
        )
        mentions = re.findall(r"\b(?:T-[A-Za-z0-9]+|CSV\d+-\d+)\b", text)
        with self.sessions() as s:
            exact = (
                list(
                    s.scalars(
                        select(Ticket.ticket_id).where(*conditions, Ticket.ticket_id.in_(mentions))
                    )
                )
                if mentions
                else []
            )
            indexed = s.scalar(
                select(Chunk.ticket_id)
                .join(Ticket)
                .where(
                    *conditions,
                    Chunk.customer_id == inquiry.customer_id,
                    Chunk.embedding_version == self.version,
                )
                .limit(1)
            )
        ids = []
        if indexed:
            try:
                vector = validate_vector(self.embed([text])[0], EMBEDDING_DIM)
                distance = func.min(Chunk.embedding.cosine_distance(vector))
                with self.sessions() as s:
                    ids = list(
                        s.scalars(
                            select(Chunk.ticket_id)
                            .join(Ticket)
                            .where(
                                *conditions,
                                Chunk.customer_id == inquiry.customer_id,
                                Chunk.embedding_version == self.version,
                            )
                            .group_by(Chunk.ticket_id)
                            .order_by(distance, Chunk.ticket_id)
                            .limit(limit)
                        )
                    )
            except Exception as exc:
                _LOG.warning("History semantic search unavailable (%s)", type(exc).__name__)
        # Exact references still work when embeddings are not yet available.
        result = []
        for previous in list(dict.fromkeys([*exact, *ids]))[:limit]:
            snapshot = self.snapshot(previous)
            if snapshot is None or snapshot[0] != inquiry.customer_id:
                continue
            _, subject, updated, sources = snapshot
            result.append(
                {
                    "ticket_id": previous,
                    "subject": subject,
                    "source_updated_at": updated.isoformat(),
                    "sources": {f"{previous}/{key}": value for key, value in sources.items()},
                }
            )
        return result

    def match(self, ticket_id, inquiry, timeout=12):
        if not inquiry.customer_id or not getattr(self.llm, "enabled", False):
            return None
        if not _CAPACITY.acquire(blocking=False):
            _LOG.info("History matching capacity exceeded")
            return None

        def work():
            candidates = self.candidates(ticket_id, inquiry)
            result = judge(customer_source(inquiry), candidates, self.llm)
            if result:
                selected = next(
                    c for c in candidates if c["ticket_id"] == result["previous_ticket_id"]
                )
                current = self.snapshot(result["previous_ticket_id"])
                if (
                    current is None
                    or current[0] != inquiry.customer_id
                    or current[2].isoformat() != selected["source_updated_at"]
                    or {f"{selected['ticket_id']}/{k}": v for k, v in current[3].items()}
                    != selected["sources"]
                ):
                    return None
            return result

        future = _POOL.submit(contextvars.copy_context().run, work)
        future.add_done_callback(lambda _: _CAPACITY.release())
        try:
            return future.result(timeout=timeout)
        except Exception as exc:
            # Timeout tasks never mutate ticket/link state after the caller has returned.
            future.cancel()
            _LOG.warning("History matching unavailable (%s)", type(exc).__name__)
            return None


async def index_loop(history: CustomerHistory):
    while True:
        try:
            count = await asyncio.to_thread(history.refresh_batch)
        except Exception as exc:
            _LOG.warning("History refresh unavailable (%s)", type(exc).__name__)
            count = 0
        await asyncio.sleep(1 if count else 30)
