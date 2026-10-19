# 문의 처리 서비스 (CSA-21 · CSA-25 · 담당 김동규)
#
# API 와 그래프 사이. 그래프 실행·재개와 기록을 묶는다.
#
# - submit(inquiry): ticket_id 발급 → graph.invoke → 상담원 검토 지점(또는 사람 큐)에서
#   멈춘 상태로 반환
# - act(ticket_id, review): 상담원 버튼 → Command(resume=...) 로 그래프 재개 (CSA-25)
# - resolve(ticket_id): 해결 확정 → 상태 RESOLVED, 저장 대상이면 사례로 남김
#   (agents/case_memory.py)
# - get(ticket_id): 그래프 상태 → TicketOut. sla_due_at = 접수 + 해결 목표 시간 (rules/sla.py)
# - work_list(dept): 열린 티켓을 SLA 경과 비율 큰 순으로, at_risk(≥ 75%) 표시 (CSA-40)
#
# 저장소: 지금은 그래프 체크포인트(메모리) + 이 객체의 dict 다. 서버를 다시 켜면 사라진다.
# TODO(CSA-24·25): PostgreSQL 이 오면 tickets·drafts·reviews 행 기록, PostgresSaver 체크포인트,
#   work_list 는 db/sql/work_list.sql 로. 사례는 resolution_cases + embedding 으로 (CSA-18).
import uuid
from datetime import UTC, datetime
from typing import Any

from langgraph.types import Command

from cs_agent.agents.case_memory import SAVE_ON, build_case
from cs_agent.domain import Route, TicketStatus
from cs_agent.llm.tracing import ticket_scope
from cs_agent.rules.sla import due_at, elapsed_hours, is_at_risk
from cs_agent.schemas import InquiryIn, ReviewIn, TicketOut

CLOSED = {TicketStatus.APPROVED, TicketStatus.REJECTED, TicketStatus.RESOLVED}


class TicketNotFound(LookupError):
    pass


class InvalidAction(ValueError):
    """지금 상태에서 할 수 없는 처리 (예: 검토 대기가 아닌데 승인)"""


class TicketService:
    def __init__(self, graph: Any) -> None:
        self.graph = graph
        self.ticket_ids: list[str] = []  # 접수 순서
        self.reviews: dict[str, list[ReviewIn]] = {}  # TODO(CSA-24): reviews 테이블
        self.cases: list[dict] = []  # TODO(CSA-18·24): resolution_cases + embedding

    @staticmethod
    def _config(ticket_id: str) -> dict:
        return {"configurable": {"thread_id": ticket_id}}

    def _state(self, ticket_id: str) -> Any:
        if ticket_id not in self.reviews:
            raise TicketNotFound(ticket_id)
        return self.graph.get_state(self._config(ticket_id))

    def submit(self, inquiry: InquiryIn) -> TicketOut:
        ticket_id = f"T-{uuid.uuid4().hex[:12].upper()}"
        self.ticket_ids.append(ticket_id)
        self.reviews[ticket_id] = []
        with ticket_scope(ticket_id):  # 문의 1건의 LLM 호출을 Langfuse trace 하나로
            self.graph.invoke({"ticket_id": ticket_id, "inquiry": inquiry}, self._config(ticket_id))
        return self.get(ticket_id)

    def act(self, ticket_id: str, review: ReviewIn) -> TicketOut:
        snapshot = self._state(ticket_id)
        if "review" not in snapshot.next:
            raise InvalidAction(f"{ticket_id} 는 상담원 검토 대기 상태가 아니다")
        self.reviews[ticket_id].append(review)
        with ticket_scope(ticket_id):
            self.graph.invoke(
                Command(resume=review.model_dump(mode="json")), self._config(ticket_id)
            )
        return self.get(ticket_id)

    def resolve(self, ticket_id: str) -> TicketOut:
        values = self._state(ticket_id).values
        if values.get("status") not in {TicketStatus.APPROVED, TicketStatus.ESCALATED}:
            raise InvalidAction(f"{ticket_id} 는 승인·이관된 문의만 해결 확정할 수 있다")
        self.graph.update_state(self._config(ticket_id), {"status": TicketStatus.RESOLVED})
        review = values.get("review")
        if review and review.action in SAVE_ON:
            self.cases.append(build_case(self._state(ticket_id).values))
        return self.get(ticket_id)

    def get(self, ticket_id: str) -> TicketOut:
        v = self._state(ticket_id).values
        rules = v.get("rules")
        classification = v.get("classification")
        extraction = v.get("extraction")
        return TicketOut(
            ticket_id=ticket_id,
            status=v.get("status", TicketStatus.NEW),
            route=Route(v["route"]) if v.get("route") else None,
            category=classification.category if classification else None,
            product_code=extraction.product_code if extraction else None,
            priority=rules.priority if rules else None,
            assigned_dept=rules.assigned_dept if rules else None,
            sla_due_at=due_at(v["inquiry"].received_at, rules.sla_resolution_h) if rules else None,
            draft=v.get("draft"),
            info_request=v.get("info_request"),
            checks=v.get("checks", []),
            evidence=v.get("evidence", []),
        )

    def work_list(self, dept: str | None = None, now: datetime | None = None) -> list[dict]:
        now = now or datetime.now(UTC)
        rows = []
        for ticket_id in self.ticket_ids:
            v = self.graph.get_state(self._config(ticket_id)).values
            rules = v.get("rules")
            if v.get("status") in CLOSED or rules is None:
                continue
            if dept and rules.assigned_dept != dept:
                continue
            # TODO(CSA-40): WAITING_CUSTOMER 동안 멈춘 시간(customer_wait_hours)을 빼기 (DB 필요)
            elapsed = elapsed_hours(v["inquiry"].received_at, now)
            rows.append(
                {
                    "ticket_id": ticket_id,
                    "status": v["status"],
                    "category": v["classification"].category,
                    "priority": rules.priority,
                    "assigned_dept": rules.assigned_dept,
                    "sla_due_at": due_at(v["inquiry"].received_at, rules.sla_resolution_h),
                    "sla_ratio": round(elapsed / rules.sla_resolution_h, 3),
                    "at_risk": is_at_risk(elapsed, rules.sla_resolution_h),
                }
            )
        return sorted(rows, key=lambda r: r["sla_ratio"], reverse=True)
