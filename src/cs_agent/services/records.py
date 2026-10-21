# 문의 기록 저장소 (CSA-24 · CSA-25 · 담당 김동규)
#
# services/tickets.py 가 그래프를 돌릴 때마다 결과를 여기 남긴다. 그래프 상태 자체는 체크포인터가
# 들고 있고, 여기는 조회·집계용 행이다 (작업 목록·대시보드·KPI, db/models.py 표 참고).
#
# - SqlRecords: PostgreSQL (tickets · drafts · reviews · resolution_cases).
#   main.py 가 DB 에 붙으면 쓴다.
# - MemoryRecords: 같은 모양의 메모리 구현. 로컬 개발(DB 없음)·테스트용. 서버를 다시 켜면 사라진다.
#
# 기록 규칙
# - save_state(): 그래프를 한 번 돌릴 때마다 tickets 행을 상태로 덮어쓴다. 추천 답변·추가정보
#   요청문이 이전 버전과 다르면 drafts 에 새 버전을 쌓는다. 한 번 실행 안에서 자동 점검 재작성이
#   여러 번 일어나면 마지막 버전만 남는다 (중간본은 체크포인트 기록에 있다).
# - add_review(): 상담원 버튼 한 번 = reviews 한 행. 그때 보고 있던 최신 버전(draft_id)에 붙인다.
# - save_case(): 해결 확정 사례 (agents/case_memory.build_case). 임베딩을 같이 넣어야 사례 검색
#   (agents/retrieval.py)에 잡힌다. LLM_PROVIDER=live 가 아니면 벡터 없이 남긴다.
# - deactivate_case(): 재문의로 다시 열린 문의의 사례를 검색에서 뺀다 (active=false).
import logging
from datetime import UTC, datetime
from typing import Any, Protocol

from cs_agent.domain import ReviewAction, TicketStatus
from cs_agent.schemas import InquiryIn, ReviewIn

_LOGGER = logging.getLogger(__name__)


class Records(Protocol):
    def add_ticket(self, ticket_id: str, inquiry: InquiryIn) -> None: ...

    def exists(self, ticket_id: str) -> bool: ...

    def ticket_ids(self, exclude: frozenset[str] = frozenset()) -> list[str]:
        """접수 순서. exclude 상태(TicketStatus 값)의 티켓은 뺀다."""
        ...

    def find_thread(self, thread_ref: str) -> str | None: ...

    def save_state(self, ticket_id: str, values: dict) -> None: ...

    def add_review(self, ticket_id: str, review: ReviewIn) -> None: ...

    def save_case(self, case: dict) -> None: ...

    def deactivate_case(self, ticket_id: str) -> None: ...


def _dump(value: Any) -> dict:
    return value.model_dump(mode="json") if value is not None else {}


def ticket_row(values: dict) -> dict:
    """그래프 상태 → tickets 행 (ticket_id 제외 열)."""
    inquiry: InquiryIn = values["inquiry"]
    classification = _dump(values.get("classification"))
    extraction = _dump(values.get("extraction"))
    rules = _dump(values.get("rules"))
    status = values.get("status") or TicketStatus.NEW
    return {
        "channel": inquiry.channel,
        "customer_id": inquiry.customer_id,
        "customer_tier": inquiry.customer_tier,
        "country": inquiry.country,
        "language": inquiry.language or extraction.get("language"),
        "subject": inquiry.subject,
        "body": inquiry.body,
        "provided_fields": dict(inquiry.provided_fields),
        "thread_ref": inquiry.thread_ref,
        "received_at": inquiry.received_at,
        "category": classification.get("category"),
        "secondary_category": classification.get("secondary_category"),
        "category_confidence": classification.get("confidence"),
        "category_model": classification.get("model"),
        "product_code": extraction.get("product_code"),
        "product_family": extraction.get("product_family"),
        "error_code": extraction.get("error_code"),
        "fw_version": extraction.get("fw_version"),
        "serial_no": extraction.get("serial_no"),
        "urgency_flag": extraction.get("urgency"),
        "return_defect": extraction.get("return_defect"),
        "provided_info": extraction.get("provided_info") or [],
        "analysis_error": values.get("analysis_error"),
        "priority": rules.get("priority"),
        "priority_rule_id": rules.get("priority_rule_id"),
        "assigned_dept": rules.get("assigned_dept"),
        "routing_rule_id": rules.get("routing_rule_id"),
        "missing_info": rules.get("missing_info") or [],
        "missing_blocking": rules.get("missing_blocking") or [],
        "sla_id": rules.get("sla_id"),
        "sla_first_response_target_h": rules.get("sla_first_response_h"),
        "sla_resolution_target_h": rules.get("sla_resolution_h"),
        "route": values.get("route"),
        "status": str(status),
        "escalated_to": values.get("escalated_to"),
        "followups": values.get("followups", 0),
    }


def draft_versions(values: dict) -> list[dict]:
    """상태에 든 추천 답변·추가정보 요청문 → drafts 행 후보 (version 제외)."""
    review = values.get("review")
    feedback = review.feedback if review and review.action == ReviewAction.REWRITE else None
    rows = []
    draft = values.get("draft")
    if draft is not None:
        rows.append(
            {
                "kind": "draft",
                "text": draft.text,
                "template": draft.template,
                "slots": dict(draft.slots),
                "cited": list(draft.cited),
                "evidence": [e.model_dump(mode="json") for e in values.get("evidence", [])],
                "checks": [c.model_dump(mode="json") for c in values.get("checks", [])],
                "reviewer_feedback": feedback,
                "model": draft.model,
            }
        )
    if values.get("info_request"):
        rows.append({"kind": "info_request", "text": values["info_request"]})
    return rows


def _now() -> datetime:
    return datetime.now(UTC)


# 메모리 ---------------------------------------------------------------------------------------


class MemoryRecords:
    def __init__(self) -> None:
        self.tickets: dict[str, dict] = {}  # 접수 순서 유지 (dict 순서)
        self.drafts: dict[str, list[dict]] = {}
        self.reviews: dict[str, list[ReviewIn]] = {}
        self.cases: list[dict] = []

    def add_ticket(self, ticket_id: str, inquiry: InquiryIn) -> None:
        self.tickets[ticket_id] = {"thread_ref": inquiry.thread_ref, "status": TicketStatus.NEW}
        self.drafts[ticket_id] = []
        self.reviews[ticket_id] = []

    def exists(self, ticket_id: str) -> bool:
        return ticket_id in self.tickets

    def ticket_ids(self, exclude: frozenset[str] = frozenset()) -> list[str]:
        return [tid for tid, row in self.tickets.items() if row["status"] not in exclude]

    def find_thread(self, thread_ref: str) -> str | None:
        return next((t for t, r in self.tickets.items() if r["thread_ref"] == thread_ref), None)

    def save_state(self, ticket_id: str, values: dict) -> None:
        self.tickets[ticket_id].update(ticket_row(values))
        versions = self.drafts[ticket_id]
        for row in draft_versions(values):
            last = next((d for d in reversed(versions) if d["kind"] == row["kind"]), None)
            if not last or last["text"] != row["text"]:
                versions.append({**row, "version": len(versions) + 1})

    def add_review(self, ticket_id: str, review: ReviewIn) -> None:
        self.reviews[ticket_id].append(review)

    def save_case(self, case: dict) -> None:
        self.cases = [c for c in self.cases if c["case_id"] != case["case_id"]] + [case]

    def deactivate_case(self, ticket_id: str) -> None:
        for case in self.cases:
            if case["ticket_id"] == ticket_id:
                case["active"] = False


# PostgreSQL -----------------------------------------------------------------------------------


class SqlRecords:
    def __init__(self, sessionmaker: Any, embed_fn: Any = None) -> None:
        self.sessionmaker = sessionmaker
        self.embed_fn = embed_fn  # 사례 임베딩. None 이면 벡터 없이 저장

    def add_ticket(self, ticket_id: str, inquiry: InquiryIn) -> None:
        from cs_agent.db.models import Ticket

        values = ticket_row({"inquiry": inquiry})
        with self.sessionmaker.begin() as s:
            s.add(Ticket(ticket_id=ticket_id, **values))

    def exists(self, ticket_id: str) -> bool:
        from cs_agent.db.models import Ticket

        with self.sessionmaker() as s:
            return s.get(Ticket, ticket_id) is not None

    def ticket_ids(self, exclude: frozenset[str] = frozenset()) -> list[str]:
        import sqlalchemy as sa

        from cs_agent.db.models import Ticket

        query = sa.select(Ticket.ticket_id).order_by(Ticket.received_at, Ticket.ticket_id)
        if exclude:
            query = query.where(Ticket.status.not_in([str(s) for s in exclude]))
        with self.sessionmaker() as s:
            return list(s.scalars(query))

    def find_thread(self, thread_ref: str) -> str | None:
        import sqlalchemy as sa

        from cs_agent.db.models import Ticket

        query = (
            sa.select(Ticket.ticket_id)
            .where(Ticket.thread_ref == thread_ref)
            .order_by(Ticket.received_at)
            .limit(1)
        )
        with self.sessionmaker() as s:
            return s.scalar(query)

    def save_state(self, ticket_id: str, values: dict) -> None:
        import sqlalchemy as sa

        from cs_agent.db.models import DraftRow, Ticket

        row = ticket_row(values)
        with self.sessionmaker.begin() as s:
            ticket = s.get(Ticket, ticket_id)
            for key, value in row.items():
                setattr(ticket, key, value)
            if row["status"] == TicketStatus.RESOLVED and ticket.resolved_at is None:
                ticket.resolved_at = _now()
            # 고객에게 처음 무언가 보낸 시점 (승인된 답변 또는 추가정보 요청)
            if (
                row["status"] in (TicketStatus.APPROVED, TicketStatus.WAITING_CUSTOMER)
                and ticket.first_responded_at is None
            ):
                ticket.first_responded_at = _now()

            version = s.scalar(
                sa.select(sa.func.coalesce(sa.func.max(DraftRow.version), 0)).where(
                    DraftRow.ticket_id == ticket_id
                )
            )
            for draft in draft_versions(values):
                last = s.scalar(
                    sa.select(DraftRow.text)
                    .where(DraftRow.ticket_id == ticket_id, DraftRow.kind == draft["kind"])
                    .order_by(DraftRow.version.desc())
                    .limit(1)
                )
                if last != draft["text"]:
                    version += 1
                    s.add(DraftRow(ticket_id=ticket_id, version=version, **draft))

    def add_review(self, ticket_id: str, review: ReviewIn) -> None:
        import sqlalchemy as sa

        from cs_agent.db.models import DraftRow, ReviewRow

        with self.sessionmaker.begin() as s:
            draft_id = s.scalar(
                sa.select(DraftRow.id)
                .where(DraftRow.ticket_id == ticket_id)
                .order_by(DraftRow.version.desc())
                .limit(1)
            )
            s.add(
                ReviewRow(
                    ticket_id=ticket_id,
                    draft_id=draft_id,
                    action=str(review.action),
                    reviewer=review.reviewer,
                    edited_text=review.edited_text,
                    feedback=review.feedback,
                    feedback_reason=review.feedback_reason and str(review.feedback_reason),
                    escalated_to=review.escalate_to,
                    info_items=list(review.info_items),
                )
            )

    def save_case(self, case: dict) -> None:
        from sqlalchemy.dialects.postgresql import insert

        from cs_agent.config import get_settings
        from cs_agent.db.models import ResolutionCase
        from cs_agent.pipeline.embed_docs import _embedding_hash

        settings = get_settings()
        values = {**case, "data_split": "live"}
        values["embedding"] = self._embed(case["text"])
        if values["embedding"] is not None:
            values["text_hash"] = _embedding_hash(
                case["text"], settings.embedding_model, settings.embedding_dim
            )
        stmt = insert(ResolutionCase).values(**values)
        stmt = stmt.on_conflict_do_update(
            index_elements=[ResolutionCase.case_id],
            set_={k: stmt.excluded[k] for k in values if k != "case_id"},
        )
        with self.sessionmaker.begin() as s:
            s.execute(stmt)

    def _embed(self, text: str) -> list[float] | None:
        if self.embed_fn is None:
            return None
        try:
            return self.embed_fn([text])[0]
        except (
            Exception
        ):  # 임베딩 장애로 해결 확정을 막지 않는다. 벡터는 embed_docs 재적재로 채운다
            _LOGGER.exception("사례 임베딩 실패 — 벡터 없이 저장")
            return None

    def deactivate_case(self, ticket_id: str) -> None:
        import sqlalchemy as sa

        from cs_agent.db.models import ResolutionCase

        with self.sessionmaker.begin() as s:
            s.execute(
                sa.update(ResolutionCase)
                .where(ResolutionCase.ticket_id == ticket_id)
                .values(active=False)
            )
