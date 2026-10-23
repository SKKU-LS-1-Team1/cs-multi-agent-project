"""Persist progress drafts and approved translations without dispatch or ticket transitions."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime

from cs_agent.agents import progress as progress_agent
from cs_agent.domain import TicketStatus
from cs_agent.llm.router import LLMRouter
from cs_agent.progress_schemas import ProgressApprovalIn, ProgressNotice, ProgressNoticeIn
from cs_agent.services.specialist_records import SpecialistConflict
from cs_agent.services.tickets import InvalidAction, TicketService


class ProgressService:
    def __init__(
        self,
        tickets: TicketService,
        llm: LLMRouter,
        *,
        generate: Callable | None = None,
        prepare: Callable | None = None,
    ) -> None:
        self.tickets = tickets
        self.llm = llm
        self.generate = generate or progress_agent.generate_notice
        self.prepare = prepare or progress_agent.prepare_notice

    @contextmanager
    def _locks(self, ticket_ids: list[str]) -> Iterator[None]:
        # The same deterministic order is used by all batch notice operations.
        try:
            with self.tickets.records.ticket_locks(ticket_ids):
                yield
        except SpecialistConflict as error:
            raise InvalidAction(str(error)) from error

    def list(self, anchor: str) -> list[ProgressNotice]:
        values = self.tickets._state(anchor).values
        return [ProgressNotice.model_validate(row) for row in values.get("progress_notices", [])]

    def _source(self, ticket_ids: list[str]) -> tuple[str, str, list[dict], str]:
        customer_ids, languages = set(), set()
        facts, revisions = [], []
        for ticket_id in ticket_ids:
            snapshot = self.tickets._state(ticket_id)
            self._save_node(snapshot)  # Reject interrupted generation before any model call.
            state = snapshot.values
            inquiry, extraction = state["inquiry"], state.get("extraction")
            customer_id = (inquiry.customer_id or "").strip()
            language = (inquiry.language or (extraction and extraction.language) or "").strip()
            if not customer_id or not language:
                raise InvalidAction("고객 ID와 고객 언어가 확인된 문의만 묶을 수 있습니다")
            customer_ids.add(customer_id)
            languages.add(language.lower().replace("_", "-"))
            requests = self.tickets.records.specialist_requests(ticket_id)
            resolution = state.get("resolution") or {}
            classification = state.get("classification")
            facts.append(
                {
                    "ticket_id": ticket_id,
                    "status": str(state["status"]),
                    "category": str(classification.category) if classification else None,
                    "product_code": extraction.product_code if extraction else None,
                    "pending_specialist_count": sum(r["reply"] is None for r in requests),
                    "received_specialist_count": sum(r["reply"] is not None for r in requests),
                    "waiting_for_customer": state["status"] == TicketStatus.WAITING_CUSTOMER,
                    "resolution_outcome": resolution.get("outcome")
                    if not resolution.get("superseded")
                    else None,
                }
            )
            revisions.append(
                {
                    "customer_revision": state.get("customer_revision", 0),
                    "specialist_revision": len(requests)
                    + sum(r["reply"] is not None for r in requests),
                    "information_reviewed_at": (state.get("information_review") or {}).get(
                        "checked_at"
                    ),
                    # Legacy checkpoints do not have customer revisions. Never reuse a notice
                    # when their inquiry has been updated through an older API worker.
                    "inquiry": inquiry.model_dump(mode="json"),
                }
            )
        if len(customer_ids) != 1 or len(languages) != 1:
            raise InvalidAction("같은 고객 ID와 같은 고객 언어의 문의만 묶어 주세요")
        customer_id, language = next(iter(customer_ids)), next(iter(languages))
        digest = hashlib.sha256(
            json.dumps([customer_id, language, facts, revisions], sort_keys=True).encode()
        ).hexdigest()
        return customer_id, language, facts, digest

    @staticmethod
    def _save_node(snapshot) -> str:
        if snapshot.next == ("review",):
            return "hold" if snapshot.values.get("status") == TicketStatus.ON_HOLD else "ready"
        if snapshot.next:
            raise InvalidAction("문의가 처리 중입니다. 분석이 끝난 뒤 다시 시도해 주세요")
        if snapshot.values.get("status") == TicketStatus.RESOLVED and (
            snapshot.values.get("approval_error") or snapshot.values.get("translation_error")
        ):
            # A closed escalation can retain a historical approval error. The finish writer
            # has a conditional edge to hold; use the unconditional terminal writer instead.
            # update_state executes writers only, so no escalation/status fields are changed.
            return "escalate"
        node = {
            TicketStatus.ANALYSIS_PENDING: "analysis_pending",
            TicketStatus.HUMAN_QUEUE: "human",
            TicketStatus.ESCALATED: "escalate",
            TicketStatus.WAITING_CUSTOMER: "finish",
            TicketStatus.APPROVED: "finish",
            TicketStatus.REJECTED: "finish",
            TicketStatus.RESOLVED: "finish",
        }.get(snapshot.values.get("status"))
        if node is None:
            raise InvalidAction("문의 상태가 확정된 뒤 진행 안내를 작성해 주세요")
        return node

    def _save(self, anchor: str, notice: ProgressNotice) -> None:
        snapshot = self.tickets._state(anchor)
        rows = list(snapshot.values.get("progress_notices", []))
        replacement = notice.model_dump(mode="json")
        for index, row in enumerate(rows):
            if row["notice_id"] == str(notice.notice_id):
                rows[index] = replacement
                break
        else:
            rows.append(replacement)
        self.tickets.graph.update_state(
            self.tickets._config(anchor),
            {"progress_notices": rows},
            as_node=self._save_node(snapshot),
        )
        # Notice metadata belongs to the durable checkpoint only. No ticket status, draft,
        # final reply, SLA timestamps or reviews are overwritten in the relational projection.

    def create(self, anchor: str, body: ProgressNoticeIn) -> ProgressNotice:
        if anchor not in body.ticket_ids:
            raise InvalidAction("기준 문의를 선택한 문의 목록에 포함해 주세요")
        with self._locks(body.ticket_ids):
            existing = next(
                (row for row in self.list(anchor) if row.notice_id == body.notice_id), None
            )
            if existing and existing.ticket_ids != body.ticket_ids:
                raise InvalidAction("같은 안내 ID에 다른 문의를 사용할 수 없습니다")
            customer, language, facts, version = self._source(body.ticket_ids)
            if existing and existing.source_version != version:
                raise InvalidAction("문의 정보가 변경되었습니다. 새 진행 안내를 생성해 주세요")
            if existing and existing.draft_text:
                return existing
            notice = existing or ProgressNotice(
                notice_id=body.notice_id,
                anchor_ticket_id=anchor,
                ticket_ids=body.ticket_ids,
                customer_id=customer,
                target_language=language,
                source_facts=facts,
                source_version=version,
                created_at=datetime.now(UTC),
            )
            try:
                notice.draft_text = self.generate(facts, self.llm)
                notice.error = None
            except progress_agent.ProgressError as error:
                notice.error = str(error)
            self._save(anchor, notice)
            return notice

    def approve(self, anchor: str, notice_id: str, body: ProgressApprovalIn) -> ProgressNotice:
        # Read immutable selection before locking; re-read the notice under all selected locks.
        selection = next((r for r in self.list(anchor) if str(r.notice_id) == notice_id), None)
        if selection is None:
            raise InvalidAction("이 문의의 진행 안내를 찾을 수 없습니다")
        with self._locks(selection.ticket_ids):
            notice = next(r for r in self.list(anchor) if str(r.notice_id) == notice_id)
            _, _, facts, version = self._source(notice.ticket_ids)
            if version != notice.source_version:
                raise InvalidAction("문의 정보가 변경되었습니다. 새 진행 안내를 생성해 주세요")
            if notice.status == "prepared":
                if notice.approved_text == body.edited_text and notice.reviewer == body.reviewer:
                    return notice
                raise InvalidAction("이미 승인된 안내입니다. 변경하려면 새 안내를 생성해 주세요")
            if not notice.draft_text:
                raise InvalidAction("영어 진행 안내 초안을 생성한 뒤 승인해 주세요")
            # Preserve the exact staff candidate if validation or translation fails.
            notice.approved_text = body.edited_text
            notice.reviewer = body.reviewer
            try:
                notice.final_text = self.prepare(
                    body.edited_text, notice.target_language, facts, self.llm
                )
                notice.status = "prepared"
                notice.approved_at = datetime.now(UTC)
                notice.error = None
            except progress_agent.ProgressError as error:
                notice.error = str(error)
            self._save(anchor, notice)
            return notice
