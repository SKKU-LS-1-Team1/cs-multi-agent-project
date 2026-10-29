# 문의 처리 서비스 (CSA-21 · CSA-25 · 담당 김동규)
#
# API 와 그래프 사이. 그래프 실행·재개와 기록을 묶는다.
#
# - submit(inquiry): ticket_id 발급 → graph.invoke → 상담원 검토 지점(또는 사람 큐)에서
#   멈춘 상태로 반환. thread_ref 가 기존 티켓과 같으면 새 티켓이 아니라 고객 회신이다 (reply).
#   language 가 없으면(웹 문의서) 제목·본문에서 감지한다 (verification.detect_language).
# - reply(ticket_id, inquiry): 고객 회신 → 원문에 회신을 붙여 같은 thread_id 로 ① 접수부터 다시
#   돈다. 재문의 횟수(followups) +1, 해결된 문의였으면 그 사례를 검색에서 뺀다.
# - act(ticket_id, review): 상담원 버튼 → Command(resume=...) 로 그래프 재개 (CSA-25)
# - resolve(ticket_id): 해결 확정 → 상태 RESOLVED, 저장 대상이면 사례로 남김
#   (agents/case_memory.py)
# - get(ticket_id): 그래프 상태 → TicketOut. sla_due_at = 접수 + 해결 목표 시간 + 고객 대기 시간
#   (rules/sla.py due_at, 대기 시간은 records.wait_hours)
# - work_list(dept, assignee): 열린 티켓을 SLA 경과 비율 큰 순으로, at_risk(≥ 75%) 표시 (CSA-40).
#   DB 가 있으면 db/sql/work_list.sql (records.work_list), 없으면 그래프 상태로 같은 규칙을
#   계산한다.
#   경과 시간에서 고객 회신 대기(WAITING_CUSTOMER) 시간을 뺀다 — 그동안 SLA 가 멈춘다.
#   규칙이 없는 사람 큐(분류 실패한 안전 건)는 맨 위에 둔다.
# - retry_pending(): 분석 대기(ANALYSIS_PENDING, LLM 장애 등) 문의를 처음부터 다시 돌린다.
#   main.py 가 analysis_retry_interval_s 마다 부른다.
# - 담당자 (CSA-53, services/assignment.py): 그래프를 돌린 뒤마다 아직 담당자가 없으면 앞단
#   글로벌 C/S 센터(assignment.OWNER_DEPT) 상담원을 자동 배정한다. 문의 부서·이관과는 따로다.
#   assign(ticket_id, AssignIn): 다른 앞단 상담원으로 넘기기. agents(dept): 재배정 후보 목록.
#   명단(roster)이 비면 배정하지 않는다.
#
# 저장소: 그래프 상태는 체크포인터(PostgresSaver, DB 없으면 메모리), 조회·집계용 행은
#   services/records.py (SqlRecords: tickets·drafts·reviews·resolution_cases, 없으면 MemoryRecords).
#   그래프를 돌릴 때마다 records.save_state() 로 tickets 행을 맞춘다.
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from functools import wraps
from typing import Any

from langgraph.types import Command

from cs_agent.agents import drafting, info_request
from cs_agent.agents import specialist_followup as followup
from cs_agent.agents.case_memory import SAVE_ON, build_case
from cs_agent.agents.escalation import ESCALATION_TARGETS, EscalationError, InvalidEscalation
from cs_agent.agents.translation import new_part, source_body
from cs_agent.agents.verification import detect_language
from cs_agent.domain import ReviewAction, Route, TicketStatus, Urgency
from cs_agent.followup_schemas import FollowupConfirmation
from cs_agent.llm.router import LLMRouter
from cs_agent.llm.tracing import ticket_scope
from cs_agent.rules.engine import apply_rules
from cs_agent.rules.investigation import investigation_info
from cs_agent.rules.sla import due_at, elapsed_hours, is_at_risk
from cs_agent.rules.tables import load_tables
from cs_agent.schemas import (
    AssignIn,
    CustomerMessage,
    Draft,
    EscalationRequest,
    InformationReview,
    InformationReviewIn,
    InquiryIn,
    ManualReplyIn,
    Resolution,
    ResolveIn,
    ReviewIn,
    SpecialistReplyIn,
    SpecialistRequestIn,
    TicketOut,
)
from cs_agent.services import assignment
from cs_agent.services.assignment import Agent
from cs_agent.services.information import apply_information_review
from cs_agent.services.records import MemoryRecords, Records
from cs_agent.services.reply_preview import context_key, review_text, target_language, valid_preview
from cs_agent.services.specialist_records import SpecialistConflict

CLOSED = frozenset({TicketStatus.APPROVED, TicketStatus.REJECTED, TicketStatus.RESOLVED})


class TicketNotFound(LookupError):
    pass


class InvalidAction(ValueError):
    """지금 상태에서 할 수 없는 처리 (예: 검토 대기가 아닌데 승인)"""


def _serialized(method):
    """Serialize graph mutations and durable specialist writes for the same ticket."""

    @wraps(method)
    def wrapped(self, ticket_id, *args, **kwargs):
        try:
            with self.records.ticket_lock(ticket_id):
                return method(self, ticket_id, *args, **kwargs)
        except SpecialistConflict as exc:
            raise InvalidAction(str(exc)) from exc

    return wrapped


def ticket_dept(values: dict) -> str | None:
    """지금 맡은 부서: 이관됐으면 이관 부서, 아니면 규칙이 정한 부서 (work_list.sql 과 같다)."""
    rules = values.get("rules")
    return values.get("escalated_to") or (rules.assigned_dept if rules else None)


class TicketService:
    def __init__(
        self,
        graph: Any,
        records: Records | None = None,
        roster: list[Agent] | None = None,
        *,
        escalation_writer: Callable[..., EscalationRequest] | None = None,
        specialist_reader: Callable | None = None,
    ) -> None:
        self.graph = graph
        self.records = records if records is not None else MemoryRecords()
        self.roster = list(roster or [])  # 담당자 명단 (data/ref/agents.csv). 비면 배정 안 함
        self.escalation_writer = escalation_writer
        self.specialist_reader = specialist_reader

    @staticmethod
    def _config(ticket_id: str) -> dict:
        return {"configurable": {"thread_id": ticket_id}}

    def _state(self, ticket_id: str) -> Any:
        if not self.records.exists(ticket_id):
            raise TicketNotFound(ticket_id)
        return self.graph.get_state(self._config(ticket_id))

    def _run(self, ticket_id: str, graph_input: Any) -> None:
        with ticket_scope(ticket_id):  # 문의 1건의 LLM 호출을 Langfuse trace 하나로
            self.graph.invoke(graph_input, self._config(ticket_id))
        values = self.graph.get_state(self._config(ticket_id)).values
        self.records.save_state(ticket_id, values)
        self._auto_assign(ticket_id, values)

    def _auto_assign(self, ticket_id: str, values: dict) -> None:
        """앞단 상담원이 아직 없으면 배정한다. 부서가 바뀌어도(이관) 담당자는 그대로다."""
        owner_dept = assignment.OWNER_DEPT
        if not self.roster or values.get("status") in CLOSED:
            return
        current = self.records.assignee_of(ticket_id)
        if any(a.agent_id == current and a.dept == owner_dept and a.active for a in self.roster):
            return
        picked = assignment.assign(
            owner_dept, self.records.open_counts(exclude=CLOSED), self.roster
        )
        if picked is None or picked == current:
            return  # 모두 찼으면 담당자 없이 둔다 (앞단 큐)
        reason = "자동 배정" if current is None else "담당자 비활성 — 자동 재배정"
        self.records.set_assignee(ticket_id, picked, reason)

    def assign(self, ticket_id: str, change: AssignIn) -> TicketOut:
        """다른 앞단 상담원으로 넘긴다. 앞단이 아닌 담당자·없는 담당자·닫힌 문의는 InvalidAction."""
        values = self._state(ticket_id).values
        if values.get("status") in CLOSED:
            raise InvalidAction(f"{ticket_id} 는 닫힌 문의라 담당자를 바꿀 수 없다")
        try:
            assignment.reassign(assignment.OWNER_DEPT, change.assignee, self.roster)
        except ValueError as e:
            raise InvalidAction(str(e)) from e
        if self.records.assignee_of(ticket_id) != change.assignee:
            self.records.set_assignee(ticket_id, change.assignee, change.reason, change.by)
        return self.get(ticket_id)

    def agents(self, dept: str | None = None) -> list[dict]:
        """담당자 목록 + 열린 건수 (재배정 선택용). dept 가 있으면 그 부서 활성 담당자만."""
        counts = self.records.open_counts(exclude=CLOSED)
        return [
            {
                "agent_id": a.agent_id,
                "name": a.name,
                "dept": a.dept,
                "active": a.active,
                "max_open": a.max_open,
                "open_count": counts.get(a.agent_id, 0),
            }
            for a in self.roster
            if dept is None or (a.dept == dept and a.active)
        ]

    def assignments(self, ticket_id: str) -> list[dict]:
        self._state(ticket_id)  # 없는 문의면 TicketNotFound
        return self.records.assignments(ticket_id)

    def submit(self, inquiry: InquiryIn) -> TicketOut:
        if inquiry.thread_ref and (existing := self.records.find_thread(inquiry.thread_ref)):
            return self.reply(existing, inquiry)
        if not inquiry.language:  # 웹 문의서는 언어를 보내지 않는다 → 회신이 영어로 나가지 않게
            inquiry = inquiry.model_copy(
                update={"language": detect_language(f"{inquiry.subject}\n{inquiry.body}")}
            )
        ticket_id = f"T-{uuid.uuid4().hex[:12].upper()}"
        self.records.add_ticket(ticket_id, inquiry)
        self._run(
            ticket_id,
            {
                "ticket_id": ticket_id,
                "inquiry": inquiry,
                "followups": 0,
                "customer_messages": [self._customer_message(inquiry, "initial")],
                "customer_revision": 0,
            },
        )
        return self.get(ticket_id)

    @staticmethod
    def _customer_message(inquiry: InquiryIn, kind: str, message_id: str | None = None) -> dict:
        return CustomerMessage(
            message_id=message_id or str(uuid.uuid4()),
            kind=kind,
            **inquiry.model_dump(
                include={
                    "body",
                    "subject",
                    "received_at",
                    "language",
                    "provided_fields",
                    "category",
                    "product_code",
                }
            ),
        ).model_dump(mode="json")

    def _customer_messages(self, ticket_id: str, values: dict) -> list[dict]:
        if values.get("customer_messages"):
            return list(values["customer_messages"])
        # Older checkpoints only kept the merged body. Do not fabricate reply boundaries.
        return [self._customer_message(values["inquiry"], "initial", f"{ticket_id}:initial")]

    @_serialized
    def reply(self, ticket_id: str, inquiry: InquiryIn) -> TicketOut:
        """고객 회신. 진행 중이던 검토는 버리고 원문 + 회신으로 처음부터 다시 판단한다."""
        self._sync_specialists(ticket_id)
        values = self._state(ticket_id).values
        if values.get("status") == TicketStatus.RESOLVED:
            self.records.deactivate_case(ticket_id)  # 다시 열린 문의의 사례는 검색에서 뺀다
        merged = merge_reply(values["inquiry"], inquiry)
        followups = values.get("followups", 0) + 1
        original = values["inquiry"]
        parts = list(values.get("translation_parts", []))
        if not parts or source_body(parts) != original.body.strip():
            parts = [new_part(original.body, original.language)]
        stamp = inquiry.received_at.strftime("%Y-%m-%d %H:%M")
        parts.append(new_part(inquiry.body, inquiry.language, f"\n\n[Customer reply {stamp}]\n"))
        resolution = values.get("resolution")
        messages = self._customer_messages(ticket_id, values)
        messages.append(self._customer_message(inquiry, "reply"))
        self._run(
            ticket_id,
            {
                "customer_messages": messages,
                "customer_revision": values.get("customer_revision", 0) + 1,
                "information_review": None,
                "information_review_refresh": False,
                "resolution": {**resolution, "superseded": True} if resolution else None,
                "resolution_case_saved": False,
                "ticket_id": ticket_id,
                "inquiry": merged,
                "followups": followups,
                "body_ko": None,
                "translation_parts": parts,
            },
        )
        return self.get(ticket_id)

    @_serialized
    def generate_escalation_request(self, ticket_id: str, to_dept: str | None = None) -> TicketOut:
        """검토 중/사람 큐에서 요청서만 생성. 승인·이관·자동 배정은 하지 않는다."""
        snapshot = self._state(ticket_id)
        status = snapshot.values.get("status")
        if status not in {
            TicketStatus.READY_FOR_REVIEW,
            TicketStatus.ON_HOLD,
            TicketStatus.HUMAN_QUEUE,
        }:
            raise InvalidAction("검토 대기 또는 사람 큐 문의에서만 요청서를 만들 수 있습니다")
        if self.escalation_writer is None:
            raise EscalationError("escalation_writer_unavailable")
        try:
            with ticket_scope(ticket_id):
                request = self.escalation_writer(
                    snapshot.values,
                    to_dept=to_dept,
                    sla_due_at=self.get(ticket_id).sla_due_at,
                )
        except InvalidEscalation as exc:
            raise InvalidAction(str(exc)) from exc
        # 호출 중 회신·승인이 있었다면 이전 문의로 만든 초안을 덮어쓰지 않는다.
        latest = self._state(ticket_id)
        if latest.config != snapshot.config:
            raise InvalidAction("문의가 변경되었습니다. 최신 내용으로 요청서를 다시 생성해 주세요")
        node = {
            TicketStatus.READY_FOR_REVIEW: "ready",
            TicketStatus.ON_HOLD: "hold",
            TicketStatus.HUMAN_QUEUE: "human",
        }[status]
        self.graph.update_state(
            self._config(ticket_id), {"escalation_request": request}, as_node=node
        )
        values = self._state(ticket_id).values
        self.records.save_state(ticket_id, values)
        return self.get(ticket_id)

    def _sync_specialists(self, ticket_id: str) -> list[dict]:
        """DB is authoritative. Recover a missed checkpoint write before any rewrite/approval."""
        requests = self.records.specialist_requests(ticket_id)
        revision = len(requests) + sum(r["reply"] is not None for r in requests)
        snapshot = self._state(ticket_id)
        if snapshot.values.get("specialist_revision", 0) == revision:
            return requests
        replies = [
            {
                **r["reply"],
                "request_id": r["request_id"],
                "to_dept": r["to_dept"],
                "request_text": r["text"],
                "created_at": r["reply"]["created_at"].isoformat(),
            }
            for r in requests
            if r["reply"]
        ]
        node = {
            TicketStatus.READY_FOR_REVIEW: "ready",
            TicketStatus.ON_HOLD: "hold",
            TicketStatus.HUMAN_QUEUE: "human",
            TicketStatus.WAITING_CUSTOMER: "finish",
        }.get(snapshot.values.get("status"))
        updates = {
            "specialist_requests": [
                {
                    **r,
                    "created_at": r["created_at"].isoformat(),
                    "reply": {**r["reply"], "created_at": r["reply"]["created_at"].isoformat()}
                    if r["reply"]
                    else None,
                }
                for r in requests
            ],
            "specialist_replies": replies,
            "specialist_revision": revision,
        }
        # A specialist reply must not erase the already sent request for customer information.
        if snapshot.values.get("pending") != "info_request":
            updates.update(
                checks=[],
                approved_reply=None,
                final_reply=None,
                translation_error=None,
                approval_cited=None,
                approval_text=None,
                approval_error=None,
                approval_checks_key=None,
                approval_review=None,
            )
        self.graph.update_state(
            self._config(ticket_id), updates, **({"as_node": node} if node else {})
        )
        self.records.save_state(ticket_id, self._state(ticket_id).values)
        return requests

    def _require_specialist_state(self, ticket_id: str) -> None:
        status = self._state(ticket_id).values.get("status")
        if status not in {
            TicketStatus.READY_FOR_REVIEW,
            TicketStatus.ON_HOLD,
            TicketStatus.HUMAN_QUEUE,
            TicketStatus.WAITING_CUSTOMER,
        }:
            raise InvalidAction("검토·회신 대기 또는 사람 큐 문의에서만 등록할 수 있습니다")

    @staticmethod
    def _check_specialist_budget(requests: list[dict], additional_chars: int) -> None:
        from cs_agent.agents.drafting import MAX_SPECIALIST_CONTEXT_CHARS

        # Reserve 512 provenance chars per request and 512 reply chars while unanswered.
        # A new request must leave room for a concise reply rather than fill the whole budget.
        # Reject before immutable storage; silently clipping could drop the actual conclusion.
        used = sum(
            len(r["text"]) + (len(r["reply"]["text"]) if r["reply"] else 512) + 512
            for r in requests
        )
        if used + additional_chars > MAX_SPECIALIST_CONTEXT_CHARS:
            raise InvalidAction(
                "전문부서 요청·회신의 전체 작성 문맥 한도를 초과합니다. "
                "저장되지 않았습니다. 요청·회신을 핵심 사실과 결론 위주로 줄여 다시 등록해 주세요"
            )

    @_serialized
    def add_specialist_request(self, ticket_id: str, body: SpecialistRequestIn) -> TicketOut:
        self._require_specialist_state(ticket_id)
        if body.to_dept not in ESCALATION_TARGETS:
            raise InvalidAction("유효한 전문부서를 선택해 주세요")
        requests = self.records.specialist_requests(ticket_id)
        if not any(r["request_id"] == str(body.request_id) for r in requests):
            self._check_specialist_budget(requests, len(body.text) + 1024)
        self.records.add_specialist_request(ticket_id, body)
        self._sync_specialists(ticket_id)
        return self.get(ticket_id)

    @_serialized
    def add_specialist_reply(
        self, ticket_id: str, request_id: str, body: SpecialistReplyIn
    ) -> TicketOut:
        self._require_specialist_state(ticket_id)
        requests = self.records.specialist_requests(ticket_id)
        target = next((r for r in requests if r["request_id"] == request_id), None)
        if target is not None and target["reply"] is None:
            self._check_specialist_budget(requests, len(body.text) - 512)
        self.records.add_specialist_reply(ticket_id, request_id, body)
        self._sync_specialists(ticket_id)
        self._read_specialist_followup(ticket_id)
        return self.get(ticket_id)

    def _followup(
        self, ticket_id: str, *, state: dict | None = None, requests: list[dict] | None = None
    ) -> dict | None:
        state = state if state is not None else self._state(ticket_id).values
        requests = requests if requests is not None else self.records.specialist_requests(ticket_id)
        result = followup.current_followup(state, requests)
        if result is not None:
            result["missing_fields"] = followup.missing_fields(result["reading"], state)
        return result

    def _save_followup(self, ticket_id: str, updates: dict) -> None:
        snapshot = self._state(ticket_id)
        node = {
            TicketStatus.READY_FOR_REVIEW: "ready",
            TicketStatus.ON_HOLD: "hold",
            TicketStatus.HUMAN_QUEUE: "human",
            TicketStatus.WAITING_CUSTOMER: "finish",
        }.get(snapshot.values.get("status"))
        if node is None or (snapshot.next and snapshot.next != ("review",)):
            raise InvalidAction("검토 또는 회신 대기 상태에서 조사 내용을 확인해 주세요")
        self.graph.update_state(self._config(ticket_id), updates, as_node=node)
        self.records.save_state(ticket_id, self._state(ticket_id).values)

    def _read_specialist_followup(self, ticket_id: str, *, retry: bool = False) -> None:
        state = self._state(ticket_id).values
        requests = self.records.specialist_requests(ticket_id)
        current = self._followup(ticket_id, state=state, requests=requests)
        if current is None or not any(r.get("reply") for r in requests):
            return
        if not retry and (current["reading"] or current["error"]):
            return
        result = {
            "source_version": current["source_version"],
            "reading": None,
            "confirmation": None,
            "error": None,
        }
        try:
            if self.specialist_reader is None:
                raise ValueError("reader unavailable")
            with ticket_scope(ticket_id):
                result["reading"] = self.specialist_reader(state, requests)
        except Exception:
            # Reply was already stored; the staff can retry or record a finding manually.
            result["error"] = "회신 자동 해석을 완료하지 못했습니다. 원문을 확인해 주세요."
        if (
            followup.source_version(
                self._state(ticket_id).values, self.records.specialist_requests(ticket_id)
            )
            != result["source_version"]
        ):
            return
        if current["confirmation"]:
            result["confirmation"] = current["confirmation"]
        self._save_followup(ticket_id, {"specialist_followup": result})

    @_serialized
    def analyze_specialist_followup(self, ticket_id: str) -> TicketOut:
        self._require_specialist_state(ticket_id)
        self._read_specialist_followup(ticket_id, retry=True)
        return self.get(ticket_id)

    @_serialized
    def confirm_specialist_finding(self, ticket_id: str, body: FollowupConfirmation) -> TicketOut:
        self._require_specialist_state(ticket_id)
        self._sync_specialists(ticket_id)
        current = self._followup(ticket_id)
        if current is None or current["source_version"] != body.source_version:
            raise InvalidAction("문의 또는 회신이 변경되었습니다. 최신 근거를 다시 확인해 주세요")
        if current["pending_replies"]:
            raise InvalidAction("아직 회신하지 않은 전문부서가 있습니다")
        requests = self.records.specialist_requests(ticket_id)
        reply = next(
            (
                r["reply"]
                for r in requests
                if r.get("reply") and str(r["reply"]["reply_id"]) == body.finding.reply_id
            ),
            None,
        )
        if not reply or body.finding.evidence not in reply["text"]:
            raise InvalidAction("현재 전문부서 회신의 판정 근거를 원문 그대로 입력해 주세요")
        state = self._state(ticket_id).values
        existing = current["confirmation"]
        if existing:
            if existing["finding"] == body.finding.model_dump():
                return self.get(ticket_id)
            raise InvalidAction("이미 확인한 판정은 새 전문부서 요청·회신으로 갱신해 주세요")
        confirmation = {**body.model_dump(), "confirmed_at": datetime.now(UTC).isoformat()}
        stored = {
            "source_version": current["source_version"],
            "reading": current["reading"],
            "confirmation": confirmation,
            "error": current["error"],
        }
        self._save_followup(
            ticket_id,
            {
                "specialist_followup": stored,
                "reply_preview": None,
                **(
                    {
                        "approved_reply": None,
                        "final_reply": None,
                        "approval_text": None,
                        "approval_checks_key": None,
                        "checks": [],
                    }
                    if state.get("pending") != "info_request"
                    else {}
                ),
                "processing_history": [
                    *state.get("processing_history", []),
                    {
                        "id": str(uuid.uuid4()),
                        "kind": "investigation_confirmed",
                        "created_at": confirmation["confirmed_at"],
                        "actor": body.reviewer,
                        "text": "전문부서 최종 판정 확인: " + body.finding.evidence,
                    },
                ],
            },
        )
        return self.get(ticket_id)

    def _require_confirmed_investigation(self, ticket_id: str) -> None:
        current = self._followup(ticket_id)
        if current is not None and current["status"] != "confirmed":
            raise InvalidAction("사내 분석 중입니다. 전문부서 최종 판정을 확인한 뒤 처리해 주세요")

    @_serialized
    def review_information(self, ticket_id: str, review: InformationReviewIn) -> TicketOut:
        values = self._state(ticket_id).values
        messages = self._customer_messages(ticket_id, values)
        latest = messages[-1]
        revision = values.get("customer_revision", 0)
        if (
            latest["kind"] != "reply"
            or review.reply_id != latest["message_id"]
            or review.customer_revision != revision
        ):
            raise InvalidAction(
                "새 고객 회신이 있습니다. 최신 회신을 확인하고 자료를 검토해 주세요"
            )
        if values.get("status") not in {
            TicketStatus.READY_FOR_REVIEW,
            TicketStatus.ON_HOLD,
            TicketStatus.HUMAN_QUEUE,
        }:
            raise InvalidAction("검토 대기 또는 사람 큐에서만 수신 자료를 확인할 수 있습니다")
        if not values.get("classification") or not values.get("extraction"):
            raise InvalidAction("분석이 완료된 뒤 자료를 확인해 주세요")
        tables = load_tables()
        try:
            extraction, fields = apply_information_review(
                values["extraction"], review.fields, tables
            )
        except ValueError as error:
            raise InvalidAction(str(error)) from error
        normalized = review.model_copy(update={"fields": fields})
        previous = values.get("information_review")
        previous_review = InformationReview.model_validate(previous) if previous else None
        if previous_review and previous_review.model_dump(
            exclude={"checked_at", "expected_reviewed_at"}
        ) == normalized.model_dump(exclude={"expected_reviewed_at"}):
            snapshot = self._state(ticket_id)
            if snapshot.next and snapshot.next != ("review",):
                self._run(ticket_id, None)  # resume an interrupted previous regeneration
            else:
                self.records.save_state(
                    ticket_id, snapshot.values
                )  # repair projection-only failure
            return self.get(ticket_id)
        if review.expected_reviewed_at != (previous_review.checked_at if previous_review else None):
            raise InvalidAction(
                "다른 담당자가 자료 확인을 변경했습니다. 최신 확인값을 읽고 다시 검토해 주세요"
            )
        record = InformationReview(
            **normalized.model_dump(), checked_at=datetime.now(UTC)
        ).model_dump(mode="json")
        rules = apply_rules(
            values["classification"], extraction, values["inquiry"].customer_tier, tables
        )
        route = (
            Route.HUMAN
            if extraction.urgency == Urgency.SAFETY
            else Route.INFO_REQUEST
            if rules.missing_blocking
            else Route.DRAFT
        )
        updates = {
            "extraction": extraction,
            "rules": rules,
            "route": route,
            "information_review": record,
            "information_reviews": [*values.get("information_reviews", []), record],
            "information_review_refresh": True,
            "draft": None,
            "drafting_error": None,
            "info_request": None,
            "escalation_request": None,
            "checks": [],
            "fix_notes": [],
            "retries": 0,
            "review": None,
            "final_reply": None,
            "approved_reply": None,
            "approval_text": None,
            "approval_error": None,
            "approval_checks_key": None,
            "approval_cited": None,
            "approval_review": None,
            "translation_error": None,
        }
        self.graph.update_state(self._config(ticket_id), updates, as_node="rules")
        self._run(ticket_id, None)
        return self.get(ticket_id)

    @_serialized
    def save_manual_reply(self, ticket_id: str, body: ManualReplyIn) -> TicketOut:
        """Use the existing review/translation path for a staff-written human-queue reply."""
        requests = self._sync_specialists(ticket_id)
        snapshot = self._state(ticket_id)
        state = snapshot.values
        if state.get("status") != TicketStatus.HUMAN_QUEUE and not (
            state.get("manual_reply") and "review" in snapshot.next
        ):
            raise InvalidAction("사람 검토 문의에서만 담당자 답변을 저장할 수 있습니다")
        if not body.text.strip():
            raise InvalidAction("답변 본문은 비워 둘 수 없습니다")
        revision = len(requests) + sum(r["reply"] is not None for r in requests)
        if any(r["reply"] is None for r in requests):
            raise InvalidAction("전문부서 회신을 모두 확인한 뒤 답변을 작성해 주세요")
        checked = state.get("information_review")
        checked_at = InformationReview.model_validate(checked).checked_at if checked else None
        if (
            body.expected_customer_revision != state.get("customer_revision", 0)
            or body.expected_specialist_revision != revision
            or body.expected_information_reviewed_at != checked_at
        ):
            raise InvalidAction("문의 정보가 변경되었습니다. 최신 회신을 확인해 주세요")
        if (
            state.get("manual_reply")
            and state.get("draft")
            and (
                state["draft"].text == body.text
                and state.get("draft_customer_revision", 0) == body.expected_customer_revision
                and state.get("draft_specialist_revision", 0) == revision
                and state.get("draft_information_reviewed_at")
                == (checked_at.isoformat() if checked_at else None)
            )
        ):
            return self.get(ticket_id)
        evidence = [e for e in state.get("evidence", []) if e.source != "specialist"]
        evidence += drafting.specialist_evidence(state.get("specialist_replies", []))
        updates = {
            "manual_reply": True,
            "draft": Draft(text=body.text, slots={"draft_language": "en"}, model="staff_review"),
            "status": TicketStatus.ON_HOLD,
            "pending": "draft",
            "evidence": evidence,
            "draft_specialist_revision": revision,
            "draft_customer_revision": state.get("customer_revision", 0),
            "draft_information_reviewed_at": checked_at.isoformat() if checked_at else None,
            "checks": [],
            "approval_text": None,
            "approval_error": None,
            "approval_checks_key": None,
            "approval_review": None,
            "approval_cited": None,
            "reply_preview": None,
            "approved_reply": None,
            "final_reply": None,
            "translation_error": None,
            "drafting_error": None,
            "info_request": None,
        }
        self.graph.update_state(self._config(ticket_id), updates, as_node="hold")
        self._run(ticket_id, None)
        return self.get(ticket_id)

    @_serialized
    def prepare_reply(self, ticket_id: str, text: str, llm: LLMRouter) -> dict:
        """Translate for staff inspection without approving or sending anything."""
        self._sync_specialists(ticket_id)
        snapshot = self._state(ticket_id)
        if "review" not in snapshot.next:
            raise InvalidAction("상담원 검토 대기 상태에서만 변환할 수 있습니다")
        state = snapshot.values
        if state.get("pending") != "info_request":
            self._require_confirmed_investigation(ticket_id)
        previous = state.get("reply_preview") or {}
        text = drafting.customer_text(text, [drafting._ref(e) for e in state.get("evidence", [])])
        if valid_preview(state, text, previous.get("preview_id")):
            return previous
        if not info_request.in_language(text, "en"):
            raise InvalidAction("영어 초안을 확인한 뒤 고객 언어로 변환해 주세요")
        language = target_language(state)
        with ticket_scope(ticket_id):
            if state.get("pending") == "info_request":
                translated = info_request.localize_request(text, language, llm)
            else:
                translated = drafting.translate_reply(text, "en", language, llm)
        if not translated or not translated.strip():
            raise drafting.TranslationError("고객 언어 변환 결과가 비어 있습니다")
        preview = {
            "preview_id": str(uuid.uuid4()),
            "source_text": text,
            "target_language": language,
            "final_text": translated,
            "context_key": context_key(state),
        }
        node = "hold" if state.get("status") == TicketStatus.ON_HOLD else "ready"
        self.graph.update_state(self._config(ticket_id), {"reply_preview": preview}, as_node=node)
        return preview

    @_serialized
    def act(self, ticket_id: str, review: ReviewIn) -> TicketOut:
        if review.acknowledged_failures and not review.reviewer.strip():
            raise InvalidAction("점검 실패를 확인하고 승인하려면 담당자 이름이 필요합니다")
        requests = self._sync_specialists(ticket_id)
        snapshot = self._state(ticket_id)
        if (
            review.expected_customer_revision is not None
            and review.expected_customer_revision != snapshot.values.get("customer_revision", 0)
        ):
            raise InvalidAction("새 고객 회신이 있습니다. 최신 내용으로 답변을 다시 검토해 주세요")
        if "expected_information_reviewed_at" in review.model_fields_set:
            current_review = snapshot.values.get("information_review")
            checked_at = (
                InformationReview.model_validate(current_review).checked_at
                if current_review
                else None
            )
            if review.expected_information_reviewed_at != checked_at:
                raise InvalidAction("자료 확인값이 변경되었습니다. 최신 초안을 다시 검토해 주세요")
        if (
            review.action in {ReviewAction.APPROVE, ReviewAction.EDIT_APPROVE}
            and snapshot.values.get("pending") != "info_request"
        ):
            self._require_confirmed_investigation(ticket_id)
            revision = len(requests) + sum(r["reply"] is not None for r in requests)
            if any(r["reply"] is None for r in requests):
                raise InvalidAction(
                    "전문부서 회신이 대기 중입니다. 회신 확인 후 답변을 작성해 주세요"
                )
            if requests and review.expected_specialist_revision != revision:
                raise InvalidAction("검토한 회신 버전이 변경되었습니다. 최신 문의를 확인해 주세요")
            if revision != snapshot.values.get("draft_specialist_revision", 0):
                raise InvalidAction("새 전문부서 회신이 있습니다. 답변을 재작성한 뒤 승인해 주세요")
        if "review" not in snapshot.next:
            raise InvalidAction(f"{ticket_id} 는 상담원 검토 대기 상태가 아니다")
        if review.reply_preview_id and not valid_preview(
            snapshot.values, review_text(snapshot.values, review), review.reply_preview_id
        ):
            raise InvalidAction(
                "초안 또는 문의 정보가 변경되었습니다. 고객 언어로 다시 변환해 주세요"
            )
        if snapshot.values.get("manual_reply") and review.action in {
            ReviewAction.REWRITE,
            ReviewAction.INFO_REQUEST,
        }:
            raise InvalidAction("사람 검토 답변은 담당자가 직접 수정해 주세요")
        request = snapshot.values.get("escalation_request")
        if review.action == ReviewAction.ESCALATE and request:
            if review.escalate_to is not None and review.escalate_to != request.to_dept:
                raise InvalidAction(
                    "이관 부서가 바뀌었습니다. 해당 부서 요청서를 다시 생성해 주세요"
                )
            if review.edited_text is not None and not review.edited_text.strip():
                raise InvalidAction("이관 요청서 본문은 비워 둘 수 없습니다")
            review = review.model_copy(update={"escalate_to": request.to_dept})
        if request and review.action in {ReviewAction.REWRITE, ReviewAction.INFO_REQUEST}:
            # 새 초안/검토 결과를 만들면 기존 요청서는 더 이상 최신이 아니다.
            node = "hold" if snapshot.values.get("status") == TicketStatus.ON_HOLD else "ready"
            self.graph.update_state(
                self._config(ticket_id), {"escalation_request": None}, as_node=node
            )
        kind = (
            "escalation"
            if review.action == ReviewAction.ESCALATE and request
            else (snapshot.values.get("pending") or "draft")
        )
        self.records.add_review(ticket_id, review, draft_kind=kind)
        self._run(ticket_id, Command(resume=review.model_dump(mode="json")))
        return self.get(ticket_id)

    @_serialized
    def resolve(self, ticket_id: str, resolution: ResolveIn | None = None) -> TicketOut:
        """Complete with confirmed results; identical retries repair partial saves safely.

        A missing body retains the pre-existing evaluation/client contract. New UI callers
        must send ResolveIn; explicitly unconfirmed closures never create a verified case.
        """
        values = self._state(ticket_id).values
        status = values.get("status")
        if status == TicketStatus.RESOLVED:
            previous = values.get("resolution")
            previous_input = (
                ResolveIn.model_validate(previous).model_dump(mode="json") if previous else None
            )
            current_input = resolution.model_dump(mode="json") if resolution else None
            if previous_input != current_input:
                raise InvalidAction(
                    "이미 완료된 문의의 처리 결과가 다릅니다. 재문의 후 다시 처리해 주세요"
                )
        elif status in {TicketStatus.APPROVED, TicketStatus.ESCALATED}:
            self._require_confirmed_investigation(ticket_id)
            record = (
                Resolution(**resolution.model_dump(), confirmed_at=datetime.now(UTC)).model_dump(
                    mode="json"
                )
                if resolution
                else None
            )
            self.graph.update_state(
                self._config(ticket_id),
                {
                    "status": TicketStatus.RESOLVED,
                    "resolution": record,
                    "resolution_case_saved": False,
                    "processing_history": [
                        *values.get("processing_history", []),
                        {
                            "id": str(uuid.uuid4()),
                            "kind": "completed",
                            "created_at": record["confirmed_at"]
                            if record
                            else datetime.now(UTC).isoformat(),
                            "actor": record["confirmed_by"] if record else "",
                            "resolution": record,
                            "text": "처리 결과 저장 및 문의 완료" if record else "문의 완료",
                        },
                    ],
                },
            )
        else:
            raise InvalidAction(f"{ticket_id} 는 승인·이관된 문의만 해결 확정할 수 있다")
        resolved = self._state(ticket_id).values
        # Persist closure before publishing the verified case. If either write fails, a same
        # payload retry reaches this path even though the checkpoint already says RESOLVED.
        self.records.save_state(ticket_id, resolved)
        if not resolved.get("resolution_case_saved", False):
            review = resolved.get("review")
            record = resolved.get("resolution")
            if record and record["outcome"] == "unconfirmed":
                self.records.deactivate_case(ticket_id)
            elif review and review.action in SAVE_ON:
                self.records.save_case(build_case(resolved))
            self.graph.update_state(self._config(ticket_id), {"resolution_case_saved": True})
        return self.get(ticket_id)

    def retry_pending(self) -> list[str]:
        """분석 대기 문의를 다시 돌리고, 대기에서 벗어난 ticket_id 를 돌려준다."""
        recovered = []
        for ticket_id in self.records.ticket_ids(exclude=CLOSED):
            values = self.graph.get_state(self._config(ticket_id)).values
            if values.get("status") != TicketStatus.ANALYSIS_PENDING:
                continue
            self._run(ticket_id, {"ticket_id": ticket_id, "inquiry": values["inquiry"]})
            if self.get(ticket_id).status != TicketStatus.ANALYSIS_PENDING:
                recovered.append(ticket_id)
        return recovered

    def get(self, ticket_id: str) -> TicketOut:
        v = self._state(ticket_id).values
        rules = v.get("rules")
        classification = v.get("classification")
        extraction = v.get("extraction")
        specialist_requests = self.records.specialist_requests(ticket_id)
        draft = v.get("draft")
        references = [drafting._ref(e) for e in v.get("evidence", [])]
        if draft:
            references += draft.cited
            draft = draft.model_copy(
                update={"text": drafting.customer_text(draft.text, references)}
            )
        return TicketOut(
            ticket_id=ticket_id,
            inquiry=v.get("inquiry"),
            body_ko=v.get("body_ko"),
            status=v.get("status", TicketStatus.NEW),
            manual_reply=v.get("manual_reply", False),
            processing_history=v.get("processing_history", []),
            assignment_history=self.records.assignments(ticket_id),
            route=Route(v["route"]) if v.get("route") else None,
            category=classification.category if classification else None,
            product_code=extraction.product_code if extraction else None,
            priority=rules.priority if rules else None,
            assigned_dept=ticket_dept(v),
            assignee=self.records.assignee_of(ticket_id),
            sla_due_at=(
                due_at(
                    v["inquiry"].received_at,
                    rules.sla_resolution_h,
                    self.records.wait_hours(ticket_id),
                )
                if rules
                else None
            ),
            draft=draft,
            info_request=v.get("info_request"),
            escalation_request=v.get("escalation_request"),
            approval_cited=v.get("approval_cited"),
            approval_text=drafting.customer_text(v["approval_text"], references)
            if v.get("approval_text") is not None
            else None,
            approval_error=v.get("approval_error"),
            customer_qc=v.get("customer_qc"),
            approved_reply=drafting.customer_text(v["approved_reply"], references)
            if v.get("approved_reply") is not None
            else None,
            final_reply=v.get("final_reply"),
            final_reply_language=(
                v["inquiry"].language or (extraction and extraction.language) or "en"
            )
            if v.get("final_reply")
            else None,
            translation_error=v.get("translation_error"),
            checks=v.get("checks", []),
            evidence=v.get("evidence", []),
            specialist_requests=specialist_requests,
            investigation_info=investigation_info(v),
            specialist_followup=self._followup(ticket_id, state=v, requests=specialist_requests),
            specialist_revision=len(specialist_requests)
            + sum(r["reply"] is not None for r in specialist_requests),
            draft_specialist_revision=v.get("draft_specialist_revision", 0),
            resolution=v.get("resolution"),
            classification=classification,
            extraction=extraction,
            rules=rules,
            field_labels={**load_tables().field_labels, **load_tables().request_labels},
            customer_messages=self._customer_messages(ticket_id, v),
            customer_revision=v.get("customer_revision", 0),
            draft_customer_revision=v.get("draft_customer_revision", 0),
            draft_information_reviewed_at=v.get("draft_information_reviewed_at"),
            information_review=v.get("information_review"),
            information_reviews=v.get("information_reviews", []),
        )

    def completed_page(self, query: str, verified: bool, offset: int, limit: int) -> dict:
        return self.records.completed_page(query, verified, offset, limit)

    def closed(self) -> list[str]:
        """Closed records are discoverable without a browser's previously loaded IDs."""
        others = frozenset(
            s for s in TicketStatus if s not in {TicketStatus.RESOLVED, TicketStatus.REJECTED}
        )
        return self.records.ticket_ids(exclude=others)

    def answered(self) -> list[str]:
        """답변을 보냈고 아직 해결 확정 전(APPROVED)인 문의, 접수 순 (관리자 화면 완료 처리용)."""
        others = frozenset(s for s in TicketStatus if s != TicketStatus.APPROVED)
        return self.records.ticket_ids(exclude=others)

    def work_list(
        self,
        dept: str | None = None,
        now: datetime | None = None,
        assignee: str | None = None,
    ) -> list[dict]:
        """assignee 를 주면 그 담당자 건만 (부서 큐·사람 큐 안전 건은 빠진다)."""
        now = now or datetime.now(UTC)
        rows = self.records.work_list(dept, assignee, now)
        if rows is not None:  # DB: db/sql/work_list.sql
            return rows
        # DB 없음(메모리 기록): 그래프 상태로 work_list.sql 과 같은 규칙을 계산한다
        rows = []
        for ticket_id in self.records.ticket_ids(exclude=CLOSED):
            v = self.graph.get_state(self._config(ticket_id)).values
            rules = v.get("rules")
            if v.get("status") in CLOSED:
                continue
            if rules is None:
                current = self.records.assignee_of(ticket_id)
                human = v.get("status") == TicketStatus.HUMAN_QUEUE or v.get("route") == Route.HUMAN
                if (
                    human
                    and (not dept or ticket_dept(v) == dept)
                    and (not assignee or current == assignee)
                ):
                    rows.append(_unruled_row(ticket_id, v, current))
                continue
            # 이관됐으면 이관 부서 목록에 보인다 (db/sql/work_list.sql 과 같다)
            assigned_dept = ticket_dept(v)
            if dept and assigned_dept != dept:
                continue
            current = self.records.assignee_of(ticket_id)
            if assignee and current != assignee:
                continue
            wait = self.records.wait_hours(ticket_id, now)  # 고객 회신 대기 동안 SLA 정지
            elapsed = elapsed_hours(v["inquiry"].received_at, now, wait)
            rows.append(
                {
                    "ticket_id": ticket_id,
                    "status": v["status"],
                    "category": v["classification"].category,
                    "priority": rules.priority,
                    "assigned_dept": assigned_dept,
                    "assignee": current,
                    "sla_due_at": due_at(v["inquiry"].received_at, rules.sla_resolution_h, wait),
                    "sla_ratio": round(elapsed / rules.sla_resolution_h, 3),
                    "at_risk": is_at_risk(elapsed, rules.sla_resolution_h),
                }
            )
        # 규칙 없는 사람 큐(sla_ratio None) 먼저, 그다음 SLA 경과 비율 큰 순
        return sorted(rows, key=lambda r: (r["sla_ratio"] is not None, -(r["sla_ratio"] or 0)))


def _unruled_row(ticket_id: str, v: dict, assignee: str | None = None) -> dict:
    """분류 없이 사람 큐로 간 안전 건. 유형·부서·SLA 는 상담원이 정한다."""
    return {
        "ticket_id": ticket_id,
        "status": v["status"],
        "category": None,
        "priority": None,
        "assigned_dept": ticket_dept(v),
        "assignee": assignee,
        "sla_due_at": None,
        "sla_ratio": None,
        "at_risk": True,
    }


def merge_reply(original: InquiryIn, reply: InquiryIn) -> InquiryIn:
    """원문 뒤에 고객 회신을 붙인다. 접수 시각(SLA 기준)은 원문 것을 쓴다."""
    stamp = reply.received_at.strftime("%Y-%m-%d %H:%M")
    return original.model_copy(
        update={
            "body": f"{original.body}\n\n[Customer reply {stamp}]\n{reply.body}".strip(),
            "language": reply.language or original.language,
            "product_code": reply.product_code or original.product_code,
            "category": reply.category or original.category,
            "provided_fields": {**original.provided_fields, **reply.provided_fields},
        }
    )
