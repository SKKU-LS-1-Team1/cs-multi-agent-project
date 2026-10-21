# 문의 처리 서비스 (CSA-21 · CSA-25 · 담당 김동규)
#
# API 와 그래프 사이. 그래프 실행·재개와 기록을 묶는다.
#
# - submit(inquiry): ticket_id 발급 → graph.invoke → 상담원 검토 지점(또는 사람 큐)에서
#   멈춘 상태로 반환. thread_ref 가 기존 티켓과 같으면 새 티켓이 아니라 고객 회신이다 (reply).
# - reply(ticket_id, inquiry): 고객 회신 → 원문에 회신을 붙여 같은 thread_id 로 ① 접수부터 다시
#   돈다. 재문의 횟수(followups) +1, 해결된 문의였으면 그 사례를 검색에서 뺀다.
# - act(ticket_id, review): 상담원 버튼 → Command(resume=...) 로 그래프 재개 (CSA-25)
# - resolve(ticket_id): 해결 확정 → 상태 RESOLVED, 저장 대상이면 사례로 남김
#   (agents/case_memory.py)
# - get(ticket_id): 그래프 상태 → TicketOut. sla_due_at = 접수 + 해결 목표 시간 (rules/sla.py)
# - work_list(dept): 열린 티켓을 SLA 경과 비율 큰 순으로, at_risk(≥ 75%) 표시 (CSA-40)
#   규칙이 없는 사람 큐(분류 실패한 안전 건)는 맨 위에 둔다.
# - retry_pending(): 분석 대기(ANALYSIS_PENDING, LLM 장애 등) 문의를 처음부터 다시 돌린다.
#   main.py 가 analysis_retry_interval_s 마다 부른다.
# - 담당자 (CSA-53, services/assignment.py): 그래프를 돌린 뒤마다 부서 안 담당자를 자동 배정한다
#   (아직 없거나, 이관으로 부서가 바뀌어 지금 담당자가 그 부서 사람이 아닐 때).
#   assign(ticket_id, AssignIn): 같은 부서 다른 담당자로 넘기기. agents(dept): 재배정 후보 목록.
#   명단(roster)이 비면 배정하지 않는다. 부서 = 이관 부서(escalated_to) 또는 assigned_dept.
#
# 저장소: 그래프 상태는 체크포인터(PostgresSaver, DB 없으면 메모리), 조회·집계용 행은
#   services/records.py (SqlRecords: tickets·drafts·reviews·resolution_cases, 없으면 MemoryRecords).
#   그래프를 돌릴 때마다 records.save_state() 로 tickets 행을 맞춘다.
# TODO(CSA-20·40): work_list 를 db/sql/work_list.sql 로 (지금은 열린 티켓의 그래프 상태로 계산).
import uuid
from datetime import UTC, datetime
from typing import Any

from langgraph.types import Command

from cs_agent.agents.case_memory import SAVE_ON, build_case
from cs_agent.agents.translation import new_part, source_body
from cs_agent.domain import Route, TicketStatus
from cs_agent.llm.tracing import ticket_scope
from cs_agent.rules.sla import due_at, elapsed_hours, is_at_risk
from cs_agent.schemas import AssignIn, InquiryIn, ReviewIn, TicketOut
from cs_agent.services import assignment
from cs_agent.services.assignment import Agent
from cs_agent.services.records import MemoryRecords, Records

CLOSED = frozenset({TicketStatus.APPROVED, TicketStatus.REJECTED, TicketStatus.RESOLVED})


class TicketNotFound(LookupError):
    pass


class InvalidAction(ValueError):
    """지금 상태에서 할 수 없는 처리 (예: 검토 대기가 아닌데 승인)"""


def ticket_dept(values: dict) -> str | None:
    """지금 맡은 부서: 이관됐으면 이관 부서, 아니면 규칙이 정한 부서 (work_list.sql 과 같다)."""
    rules = values.get("rules")
    return values.get("escalated_to") or (rules.assigned_dept if rules else None)


class TicketService:
    def __init__(
        self, graph: Any, records: Records | None = None, roster: list[Agent] | None = None
    ) -> None:
        self.graph = graph
        self.records = records if records is not None else MemoryRecords()
        self.roster = list(roster or [])  # 담당자 명단 (data/ref/agents.csv). 비면 배정 안 함

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
        """부서가 정해졌는데 그 부서 담당자가 없으면 배정한다. 이관으로 부서가 바뀌면 다시."""
        dept = ticket_dept(values)
        if not self.roster or not dept or values.get("status") in CLOSED:
            return
        current = self.records.assignee_of(ticket_id)
        if any(a.agent_id == current and a.dept == dept and a.active for a in self.roster):
            return
        picked = assignment.assign(dept, self.records.open_counts(exclude=CLOSED), self.roster)
        if picked == current:
            return
        if current is None:
            reason = "자동 배정"
        elif picked is None:
            reason = f"{dept} 로 넘어감 — 받을 담당자 없음 (부서 큐)"
        else:
            reason = f"{dept} 로 넘어가 자동 재배정"
        self.records.set_assignee(ticket_id, picked, reason)

    def assign(self, ticket_id: str, change: AssignIn) -> TicketOut:
        """같은 부서 다른 담당자로 넘긴다. 다른 부서·없는 담당자·닫힌 문의는 InvalidAction."""
        values = self._state(ticket_id).values
        if values.get("status") in CLOSED:
            raise InvalidAction(f"{ticket_id} 는 닫힌 문의라 담당자를 바꿀 수 없다")
        dept = ticket_dept(values)
        if not dept:
            raise InvalidAction(f"{ticket_id} 는 부서가 정해지지 않았다 (유형·부서를 먼저 정한다)")
        try:
            assignment.reassign(dept, change.assignee, self.roster)
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
        ticket_id = f"T-{uuid.uuid4().hex[:12].upper()}"
        self.records.add_ticket(ticket_id, inquiry)
        self._run(ticket_id, {"ticket_id": ticket_id, "inquiry": inquiry, "followups": 0})
        return self.get(ticket_id)

    def reply(self, ticket_id: str, inquiry: InquiryIn) -> TicketOut:
        """고객 회신. 진행 중이던 검토는 버리고 원문 + 회신으로 처음부터 다시 판단한다."""
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
        self._run(
            ticket_id,
            {
                "ticket_id": ticket_id,
                "inquiry": merged,
                "followups": followups,
                "body_ko": None,
                "translation_parts": parts,
            },
        )
        return self.get(ticket_id)

    def act(self, ticket_id: str, review: ReviewIn) -> TicketOut:
        snapshot = self._state(ticket_id)
        if "review" not in snapshot.next:
            raise InvalidAction(f"{ticket_id} 는 상담원 검토 대기 상태가 아니다")
        self.records.add_review(ticket_id, review)
        self._run(ticket_id, Command(resume=review.model_dump(mode="json")))
        return self.get(ticket_id)

    def resolve(self, ticket_id: str) -> TicketOut:
        values = self._state(ticket_id).values
        if values.get("status") not in {TicketStatus.APPROVED, TicketStatus.ESCALATED}:
            raise InvalidAction(f"{ticket_id} 는 승인·이관된 문의만 해결 확정할 수 있다")
        self.graph.update_state(self._config(ticket_id), {"status": TicketStatus.RESOLVED})
        resolved = self._state(ticket_id).values
        self.records.save_state(ticket_id, resolved)
        review = values.get("review")
        if review and review.action in SAVE_ON:
            self.records.save_case(build_case(resolved))
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
        return TicketOut(
            ticket_id=ticket_id,
            body_ko=v.get("body_ko"),
            status=v.get("status", TicketStatus.NEW),
            route=Route(v["route"]) if v.get("route") else None,
            category=classification.category if classification else None,
            product_code=extraction.product_code if extraction else None,
            priority=rules.priority if rules else None,
            assigned_dept=ticket_dept(v),
            assignee=self.records.assignee_of(ticket_id),
            sla_due_at=due_at(v["inquiry"].received_at, rules.sla_resolution_h) if rules else None,
            draft=v.get("draft"),
            info_request=v.get("info_request"),
            approved_reply=v.get("approved_reply"),
            final_reply=v.get("final_reply"),
            final_reply_language=(
                v["inquiry"].language or (extraction and extraction.language) or "en"
            )
            if v.get("final_reply")
            else None,
            translation_error=v.get("translation_error"),
            checks=v.get("checks", []),
            evidence=v.get("evidence", []),
        )

    def work_list(
        self,
        dept: str | None = None,
        now: datetime | None = None,
        assignee: str | None = None,
    ) -> list[dict]:
        """assignee 를 주면 그 담당자 건만 (부서 큐·사람 큐 안전 건은 빠진다)."""
        now = now or datetime.now(UTC)
        rows = []
        for ticket_id in self.records.ticket_ids(exclude=CLOSED):
            v = self.graph.get_state(self._config(ticket_id)).values
            rules = v.get("rules")
            if v.get("status") in CLOSED:
                continue
            if rules is None:
                if v.get("status") == TicketStatus.HUMAN_QUEUE and not dept and not assignee:
                    rows.append(_unruled_row(ticket_id, v))
                continue
            # 이관됐으면 이관 부서 목록에 보인다 (db/sql/work_list.sql 과 같다)
            assigned_dept = ticket_dept(v)
            if dept and assigned_dept != dept:
                continue
            current = self.records.assignee_of(ticket_id)
            if assignee and current != assignee:
                continue
            # TODO(CSA-40): WAITING_CUSTOMER 동안 멈춘 시간(customer_wait_hours)을 빼기 (DB 필요)
            elapsed = elapsed_hours(v["inquiry"].received_at, now)
            rows.append(
                {
                    "ticket_id": ticket_id,
                    "status": v["status"],
                    "category": v["classification"].category,
                    "priority": rules.priority,
                    "assigned_dept": assigned_dept,
                    "assignee": current,
                    "sla_due_at": due_at(v["inquiry"].received_at, rules.sla_resolution_h),
                    "sla_ratio": round(elapsed / rules.sla_resolution_h, 3),
                    "at_risk": is_at_risk(elapsed, rules.sla_resolution_h),
                }
            )
        # 규칙 없는 사람 큐(sla_ratio None) 먼저, 그다음 SLA 경과 비율 큰 순
        return sorted(rows, key=lambda r: (r["sla_ratio"] is not None, -(r["sla_ratio"] or 0)))


def _unruled_row(ticket_id: str, v: dict) -> dict:
    """분류 없이 사람 큐로 간 안전 건. 유형·부서·SLA 는 상담원이 정한다."""
    return {
        "ticket_id": ticket_id,
        "status": v["status"],
        "category": None,
        "priority": None,
        "assigned_dept": None,
        "assignee": None,
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
            "category": original.category or reply.category,
            "provided_fields": {**original.provided_fields, **reply.provided_fields},
        }
    )
