"""문의 처리 서비스: 그래프 실행·재개와 저장소를 묶는다 (CSA-21 · CSA-25).

TODO(CSA-24): 메모리 저장소를 PostgreSQL(db/models.py)로 바꾼다.
"""

from datetime import UTC, datetime
from uuid import uuid4

from langgraph.types import Command

from cs_agent.agents.case_memory import SAVE_ON, build_case
from cs_agent.domain import TicketStatus
from cs_agent.graph.builder import GraphDeps, build_ticket_graph
from cs_agent.rules.sla import due_at, elapsed_hours, is_at_risk, sla_ratio
from cs_agent.schemas import InquiryIn, ReviewIn, TicketOut


class TicketService:
    def __init__(self, deps: GraphDeps | None = None) -> None:
        self.graph = build_ticket_graph(deps)
        self.received_at: dict[str, datetime] = {}
        self.review_log: list[dict] = []  # 피드백 기록 (기획서 6·7장)
        self.cases: list[dict] = []  # 사례 DB 적재 대기 (기획서 7.1)

    @staticmethod
    def _config(ticket_id: str) -> dict:
        return {"configurable": {"thread_id": ticket_id}}

    def _state(self, ticket_id: str) -> dict:
        snapshot = self.graph.get_state(self._config(ticket_id))
        if not snapshot.values:
            raise KeyError(ticket_id)
        return snapshot.values

    def submit(self, inquiry: InquiryIn) -> TicketOut:
        ticket_id = f"T-{uuid4().hex[:10]}"
        self.received_at[ticket_id] = inquiry.received_at or datetime.now(UTC)
        self.graph.invoke({"ticket_id": ticket_id, "inquiry": inquiry}, self._config(ticket_id))
        return self.get(ticket_id)

    def act(self, ticket_id: str, review: ReviewIn) -> TicketOut:
        before = self._state(ticket_id)
        self.graph.invoke(Command(resume=review.model_dump(mode="json")), self._config(ticket_id))
        draft = before.get("draft")
        self.review_log.append(
            {
                "ticket_id": ticket_id,
                "action": review.action,
                "reviewer": review.reviewer,
                "original": draft.text if draft else None,
                "edited": review.edited_text,
                "feedback": review.feedback,
                "feedback_reason": review.feedback_reason,
                "at": datetime.now(UTC),
            }
        )
        return self.get(ticket_id)

    def resolve(self, ticket_id: str) -> TicketOut:
        """해결 확정 시 사례 DB에 저장한다. TODO(CSA-25): 상태를 DB에 기록."""
        state = self._state(ticket_id)
        last = next((r for r in reversed(self.review_log) if r["ticket_id"] == ticket_id), None)
        if last and last["action"] in SAVE_ON:
            self.cases.append(build_case(state))
        self.graph.update_state(self._config(ticket_id), {"status": TicketStatus.RESOLVED})
        return self.get(ticket_id)

    def get(self, ticket_id: str) -> TicketOut:
        s = self._state(ticket_id)
        rules = s.get("rules")
        received = self.received_at.get(ticket_id)
        return TicketOut(
            ticket_id=ticket_id,
            status=s.get("status", TicketStatus.NEW),
            route=s.get("route"),
            category=s["classification"].category if s.get("classification") else None,
            product_code=s["extraction"].product_code if s.get("extraction") else None,
            priority=rules.priority if rules else None,
            assigned_dept=s.get("escalated_to") or (rules.assigned_dept if rules else None),
            sla_due_at=due_at(received, rules.sla_resolution_h) if rules and received else None,
            draft=s.get("draft"),
            info_request=s.get("info_request"),
            checks=s.get("checks", []),
            evidence=s.get("evidence", []),
        )

    def work_list(self, dept: str | None = None) -> list[dict]:
        """상담원 작업 목록: SLA 남은 비율 순 정렬, 75% 이상 경고 (CSA-40)."""
        now = datetime.now(UTC)
        rows = []
        for ticket_id, received in self.received_at.items():
            t = self.get(ticket_id)
            if dept and t.assigned_dept != dept:
                continue
            s = self._state(ticket_id)
            target = s["rules"].sla_resolution_h if s.get("rules") else 0
            elapsed = elapsed_hours(received, now)
            row = t.model_dump(
                include={
                    "ticket_id",
                    "status",
                    "category",
                    "priority",
                    "assigned_dept",
                    "sla_due_at",
                }
            )
            row["sla_ratio"] = round(sla_ratio(elapsed, target), 3)
            row["at_risk"] = is_at_risk(elapsed, target)
            rows.append(row)
        return sorted(rows, key=lambda r: -r["sla_ratio"])
