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
#   (agents/retrieval.py)에 잡힌다. LLM_PROVIDER=live 가 아니거나 임베딩이 실패하면 벡터 없이
#   남기고, embed_missing_cases() 가 나중에 채운다 (main.py 주기 작업, CSA-15).
# - live_cases(): 운영 중 해결된 사례 (active 만). 키워드 검색(case_memory.LiveCasesRetriever)용.
# - deactivate_case(): 재문의로 다시 열린 문의의 사례를 검색에서 뺀다 (active=false).
# - set_assignee(): 담당자 배정·재배정 (CSA-53). tickets.assignee 를 바꾸고 assignments 에 이력을
#   한 행 남긴다. assignee 는 그래프 상태에 없어서 save_state() 가 덮어쓰지 않는다.
#   assignee_of() · open_counts()(담당자별 열린 건수, 자동 배정용) · assignments() 로 읽는다.
# - 고객 대기(CSA-40): save_state() 가 상태를 보고 SLA 정지 시간을 남긴다. WAITING_CUSTOMER 가 되면
#   waiting_since = 지금, 풀리면 그동안의 시간을 customer_wait_hours 에 더하고 waiting_since 를
#   비운다 (next_wait). wait_hours() 는 끝난 대기 + 지금 대기 중이면 그 시간.
# - work_list(): 작업 목록. SqlRecords 는 db/sql/work_list.sql 결과, MemoryRecords 는 None
#   (services/tickets.py 가 그래프 상태로 같은 규칙을 계산한다).
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

    def add_review(
        self, ticket_id: str, review: ReviewIn, *, draft_kind: str | None = None
    ) -> None: ...

    def save_case(self, case: dict) -> None: ...

    def live_cases(self) -> list[dict]:
        """운영 중 해결된 사례 (build_case 모양, active 만)."""
        ...

    def embed_missing_cases(self, limit: int = 50) -> int:
        """벡터 없이 저장된 운영 사례를 임베딩한다. 채운 건수."""
        ...

    def deactivate_case(self, ticket_id: str) -> None: ...

    def set_assignee(
        self, ticket_id: str, assignee: str | None, reason: str = "", by: str = ""
    ) -> None: ...

    def assignee_of(self, ticket_id: str) -> str | None: ...

    def open_counts(self, exclude: frozenset[str] = frozenset()) -> dict[str, int]:
        """담당자별 열린 건수. exclude 상태(닫힌 상태)의 티켓은 세지 않는다."""
        ...

    def assignments(self, ticket_id: str) -> list[dict]:
        """배정 이력 (오래된 순): from_assignee · to_assignee · reason · assigned_by · created_at"""
        ...

    def wait_hours(self, ticket_id: str, now: datetime | None = None) -> float:
        """SLA 가 멈춘 고객 대기 시간 (끝난 대기 누적 + 지금 대기 중이면 그 시간)."""
        ...

    def work_list(self, dept: str | None, assignee: str | None, now: datetime) -> list[dict] | None:
        """작업 목록 행. 계산할 수 없으면(DB 없음) None — 서비스가 그래프 상태로 계산한다."""
        ...


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
        "body_ko": values.get("body_ko"),
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
    if request := values.get("escalation_request"):
        rows.append(
            {
                "kind": "escalation",
                "text": request.text,
                "slots": request.model_dump(mode="json"),
                "cited": list(request.cited),
                "model": request.model,
                "evidence": [e.model_dump(mode="json") for e in values.get("evidence", [])],
                "checks": [c.model_dump(mode="json") for c in values.get("checks", [])],
            }
        )
    return rows


def _now() -> datetime:
    return datetime.now(UTC)


def next_wait(
    status: str, waiting_since: datetime | None, wait_hours: float, now: datetime
) -> tuple[datetime | None, float]:
    """새 상태 → (waiting_since, customer_wait_hours). 고객 회신 대기 동안 SLA 가 멈춘다."""
    if status == TicketStatus.WAITING_CUSTOMER:
        return waiting_since or now, wait_hours
    return None, current_wait(waiting_since, wait_hours, now)  # 대기가 끝났으면 그 시간을 더한다


def current_wait(waiting_since: datetime | None, wait_hours: float, now: datetime) -> float:
    if waiting_since is None:
        return wait_hours
    return wait_hours + max((now - waiting_since).total_seconds(), 0) / 3600


# 메모리 ---------------------------------------------------------------------------------------


class MemoryRecords:
    def __init__(self) -> None:
        self.tickets: dict[str, dict] = {}  # 접수 순서 유지 (dict 순서)
        self.drafts: dict[str, list[dict]] = {}
        self.reviews: dict[str, list[ReviewIn]] = {}
        self.cases: list[dict] = []
        self.assignment_log: dict[str, list[dict]] = {}

    def add_ticket(self, ticket_id: str, inquiry: InquiryIn) -> None:
        self.tickets[ticket_id] = {
            "thread_ref": inquiry.thread_ref,
            "status": TicketStatus.NEW,
            "assignee": None,
            "waiting_since": None,
            "customer_wait_hours": 0.0,
        }
        self.drafts[ticket_id] = []
        self.reviews[ticket_id] = []
        self.assignment_log[ticket_id] = []

    def exists(self, ticket_id: str) -> bool:
        return ticket_id in self.tickets

    def ticket_ids(self, exclude: frozenset[str] = frozenset()) -> list[str]:
        return [tid for tid, row in self.tickets.items() if row["status"] not in exclude]

    def find_thread(self, thread_ref: str) -> str | None:
        return next((t for t, r in self.tickets.items() if r["thread_ref"] == thread_ref), None)

    def save_state(self, ticket_id: str, values: dict) -> None:
        row = ticket_row(values)
        ticket = self.tickets[ticket_id]
        ticket["waiting_since"], ticket["customer_wait_hours"] = next_wait(
            row["status"], ticket["waiting_since"], ticket["customer_wait_hours"], _now()
        )
        ticket.update(row)
        versions = self.drafts[ticket_id]
        for row in draft_versions(values):
            last = next((d for d in reversed(versions) if d["kind"] == row["kind"]), None)
            if not last or last["text"] != row["text"]:
                versions.append({**row, "version": len(versions) + 1})

    def add_review(
        self, ticket_id: str, review: ReviewIn, *, draft_kind: str | None = None
    ) -> None:
        self.reviews[ticket_id].append(review)

    def save_case(self, case: dict) -> None:
        self.cases = [c for c in self.cases if c["case_id"] != case["case_id"]] + [case]

    def live_cases(self) -> list[dict]:
        return [dict(c) for c in self.cases if c.get("active", True)]

    def embed_missing_cases(self, limit: int = 50) -> int:
        return 0  # 메모리 모드는 벡터 검색이 없다 (LiveCasesRetriever 가 키워드로 찾는다)

    def deactivate_case(self, ticket_id: str) -> None:
        for case in self.cases:
            if case["ticket_id"] == ticket_id:
                case["active"] = False

    def set_assignee(
        self, ticket_id: str, assignee: str | None, reason: str = "", by: str = ""
    ) -> None:
        row = self.tickets[ticket_id]
        self.assignment_log[ticket_id].append(
            {
                "from_assignee": row["assignee"],
                "to_assignee": assignee,
                "reason": reason,
                "assigned_by": by,
                "created_at": _now(),
            }
        )
        row["assignee"] = assignee

    def assignee_of(self, ticket_id: str) -> str | None:
        return self.tickets[ticket_id]["assignee"]

    def open_counts(self, exclude: frozenset[str] = frozenset()) -> dict[str, int]:
        counts: dict[str, int] = {}
        for row in self.tickets.values():
            if row["assignee"] and row["status"] not in exclude:
                counts[row["assignee"]] = counts.get(row["assignee"], 0) + 1
        return counts

    def assignments(self, ticket_id: str) -> list[dict]:
        return [dict(a) for a in self.assignment_log.get(ticket_id, [])]

    # PostgreSQL -----------------------------------------------------------------------------------

    def wait_hours(self, ticket_id: str, now: datetime | None = None) -> float:
        ticket = self.tickets[ticket_id]
        return current_wait(ticket["waiting_since"], ticket["customer_wait_hours"], now or _now())

    def work_list(self, dept: str | None, assignee: str | None, now: datetime) -> list[dict] | None:
        return None  # DB 가 없으면 services/tickets.py 가 그래프 상태로 계산한다


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
            ticket.waiting_since, ticket.customer_wait_hours = next_wait(
                row["status"], ticket.waiting_since, ticket.customer_wait_hours or 0.0, _now()
            )
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

    def add_review(
        self, ticket_id: str, review: ReviewIn, *, draft_kind: str | None = None
    ) -> None:
        import sqlalchemy as sa

        from cs_agent.db.models import DraftRow, ReviewRow

        with self.sessionmaker.begin() as s:
            draft_id = s.scalar(
                sa.select(DraftRow.id)
                .where(DraftRow.ticket_id == ticket_id)
                # 최신 행이 아니라 실제 검토한 종류의 최신 버전에 연결한다.
                .where(DraftRow.kind == draft_kind if draft_kind else sa.true())
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

    def live_cases(self) -> list[dict]:
        import sqlalchemy as sa

        from cs_agent.db.models import ResolutionCase

        columns = (
            "case_id ticket_id text summary product_code product_family category error_code "
            "cause action final_reply cited active"
        ).split()
        query = (
            sa.select(*(getattr(ResolutionCase, c) for c in columns))
            .where(ResolutionCase.data_split == "live", ResolutionCase.active)
            .order_by(ResolutionCase.case_id)
        )
        with self.sessionmaker() as s:
            return [dict(row) for row in s.execute(query).mappings()]

    def embed_missing_cases(self, limit: int = 50) -> int:
        """벡터 없는 운영 사례(active)를 limit 건까지 임베딩한다. 한 건이 실패하면 거기서 멈춘다."""
        import sqlalchemy as sa

        from cs_agent.config import get_settings
        from cs_agent.db.models import ResolutionCase
        from cs_agent.pipeline.embed_docs import _embedding_hash

        if self.embed_fn is None:
            return 0
        settings = get_settings()
        query = (
            sa.select(ResolutionCase.case_id, ResolutionCase.text)
            .where(
                ResolutionCase.data_split == "live",
                ResolutionCase.active,
                ResolutionCase.embedding.is_(None),
            )
            .order_by(ResolutionCase.case_id)
            .limit(limit)
        )
        with self.sessionmaker() as s:
            pending = list(s.execute(query))
        filled = 0
        for case_id, text in pending:
            vector = self._embed(text)
            if vector is None:
                break  # 임베딩 장애 — 다음 주기에 다시
            with self.sessionmaker.begin() as s:
                s.execute(
                    sa.update(ResolutionCase)
                    .where(ResolutionCase.case_id == case_id)
                    .values(
                        embedding=vector,
                        text_hash=_embedding_hash(
                            text, settings.embedding_model, settings.embedding_dim
                        ),
                    )
                )
            filled += 1
        return filled

    def _embed(self, text: str) -> list[float] | None:
        if self.embed_fn is None:
            return None
        try:
            return self.embed_fn([text])[0]
        except Exception:  # 임베딩 장애로 해결 확정을 막지 않는다. embed_missing_cases 가 채운다
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

    def set_assignee(
        self, ticket_id: str, assignee: str | None, reason: str = "", by: str = ""
    ) -> None:
        from cs_agent.db.models import AssignmentRow, Ticket

        with self.sessionmaker.begin() as s:
            ticket = s.get(Ticket, ticket_id, with_for_update=True)
            s.add(
                AssignmentRow(
                    ticket_id=ticket_id,
                    from_assignee=ticket.assignee,
                    to_assignee=assignee,
                    reason=reason,
                    assigned_by=by,
                )
            )
            ticket.assignee = assignee

    def assignee_of(self, ticket_id: str) -> str | None:
        import sqlalchemy as sa

        from cs_agent.db.models import Ticket

        with self.sessionmaker() as s:
            return s.scalar(sa.select(Ticket.assignee).where(Ticket.ticket_id == ticket_id))

    def open_counts(self, exclude: frozenset[str] = frozenset()) -> dict[str, int]:
        import sqlalchemy as sa

        from cs_agent.db.models import Ticket

        query = (
            sa.select(Ticket.assignee, sa.func.count())
            .where(Ticket.assignee.is_not(None))
            .group_by(Ticket.assignee)
        )
        if exclude:
            query = query.where(Ticket.status.not_in([str(s) for s in exclude]))
        with self.sessionmaker() as s:
            return {assignee: n for assignee, n in s.execute(query)}

    def assignments(self, ticket_id: str) -> list[dict]:
        import sqlalchemy as sa

        from cs_agent.db.models import AssignmentRow

        query = (
            sa.select(AssignmentRow)
            .where(AssignmentRow.ticket_id == ticket_id)
            .order_by(AssignmentRow.id)
        )
        with self.sessionmaker() as s:
            return [
                {
                    "from_assignee": a.from_assignee,
                    "to_assignee": a.to_assignee,
                    "reason": a.reason,
                    "assigned_by": a.assigned_by,
                    "created_at": a.created_at,
                }
                for a in s.scalars(query)
            ]

    def wait_hours(self, ticket_id: str, now: datetime | None = None) -> float:
        from cs_agent.db.models import Ticket

        with self.sessionmaker() as s:
            ticket = s.get(Ticket, ticket_id)
            return current_wait(
                ticket.waiting_since, ticket.customer_wait_hours or 0.0, now or _now()
            )

    def work_list(self, dept: str | None, assignee: str | None, now: datetime) -> list[dict] | None:
        from cs_agent.db.queries import run

        with self.sessionmaker() as s:
            return run(
                s.connection(), "work_list", "work_list", dept=dept, assignee=assignee, now=now
            )
