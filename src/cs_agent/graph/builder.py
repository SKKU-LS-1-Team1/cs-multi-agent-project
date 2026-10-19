"""문의 처리 그래프 조립 (CSA-21 · 담당 김동규).

```
START → ① intake ─┬─ ② classify ─┐
                  ├─ ③ extract  ──┼→ ⑤ rules → ⑥ route ─┬ human ─────────────→ END
                  └─ ④ retrieve ─┘                       ├ info_request → ⑦ → ready → review
                                                         └ draft → ⑧ evidence → ⑨ draft → ⑩ verify
⑩ verify ─┬ 통과 → ready → review (interrupt: 상담원 버튼)
          ├ 실패·재시도 남음 → ⑨ draft
          └ 실패·재시도 초과 → hold → review
review ─┬ approve / edit_approve → finish → END
        ├ rewrite → ⑨ draft (상담원 피드백 포함)
        ├ info_request → ⑦ info_request → review
        ├ escalate → escalate → END
        └ reject → finish → END
```
"""

from dataclasses import dataclass, field
from uuid import uuid4

from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from cs_agent import domain, schemas
from cs_agent.agents import analysis, drafting, retrieval, verification
from cs_agent.agents.info_request import write_info_request
from cs_agent.config import get_settings
from cs_agent.domain import ReviewAction, Route, TicketStatus, Urgency
from cs_agent.graph.state import TicketState
from cs_agent.llm.router import LLMRouter, get_router
from cs_agent.rules.engine import apply_rules
from cs_agent.rules.tables import RefTables, load_tables
from cs_agent.schemas import ReviewIn


@dataclass
class GraphDeps:
    llm: LLMRouter = field(default_factory=get_router)
    docs: retrieval.Retriever | None = None
    cases: retrieval.Retriever | None = None
    tables: RefTables = field(default_factory=load_tables)
    max_retries: int = field(default_factory=lambda: get_settings().max_verify_retries)

    def __post_init__(self) -> None:
        if self.docs is None or self.cases is None:
            docs, cases = retrieval.default_retrievers()
            self.docs = self.docs or docs
            self.cases = self.cases or cases


def checkpoint_serde() -> JsonPlusSerializer:
    """체크포인트에 저장해도 되는 타입을 명시한다 (domain·schemas의 Enum·모델)."""
    allowed = [
        (mod.__name__, name)
        for mod in (domain, schemas)
        for name, obj in vars(mod).items()
        if isinstance(obj, type) and obj.__module__ == mod.__name__
    ]
    return JsonPlusSerializer(allowed_msgpack_modules=allowed)


def _text(state: TicketState) -> str:
    inquiry = state["inquiry"]
    return f"{inquiry.subject}\n{inquiry.body}".strip()


def build_ticket_graph(deps: GraphDeps | None = None, checkpointer=None):
    deps = deps or GraphDeps()

    # ① 접수 (C-01, C-09). TODO(CSA-21): thread_ref로 기존 미해결 티켓에 붙이고 재문의 +1
    def intake(state: TicketState) -> TicketState:
        return {
            "ticket_id": state.get("ticket_id") or f"T-{uuid4().hex[:10]}",
            "status": TicketStatus.NEW,
            "retries": 0,
            "review_rounds": 0,
        }

    def classify(state: TicketState) -> TicketState:
        return {"classification": analysis.classify(state["inquiry"], deps.llm)}

    def extract(state: TicketState) -> TicketState:
        return {"extraction": analysis.extract(state["inquiry"], deps.tables)}

    def retrieve(state: TicketState) -> TicketState:
        return {"candidates": retrieval.first_pass(deps.docs, deps.cases, _text(state))}

    def rules(state: TicketState) -> TicketState:
        result = apply_rules(
            state["classification"],
            state["extraction"],
            state["inquiry"].customer_tier,
            deps.tables,
        )
        if state["extraction"].urgency == Urgency.SAFETY:
            route = Route.HUMAN
        elif result.missing_blocking:
            route = Route.INFO_REQUEST
        else:
            route = Route.DRAFT
        return {"rules": result, "route": route}

    def human_queue(state: TicketState) -> TicketState:
        return {"status": TicketStatus.HUMAN_QUEUE, "draft": None}

    def info_request(state: TicketState) -> TicketState:
        review = state.get("review")
        items = (review.info_items if review else None) or state["rules"].missing_blocking
        items = items or state["rules"].missing_info
        text = write_info_request(items, state["extraction"].language, _text(state)[:300], deps.llm)
        return {"info_request": text, "pending": "info_request"}

    def evidence(state: TicketState) -> TicketState:
        return {"evidence": retrieval.finalize_evidence(state["candidates"], state["extraction"])}

    def draft(state: TicketState) -> TicketState:
        failed = [c.reason for c in state.get("checks", []) if not c.passed]
        review = state.get("review")
        feedback = review.feedback if review and review.action == ReviewAction.REWRITE else None
        result = drafting.write_draft(
            state["classification"].category,
            state["extraction"],
            state["evidence"],
            _text(state),
            deps.llm,
            fix_notes=failed or None,
            reviewer_feedback=feedback,
        )
        return {"draft": result, "pending": "draft", "review": None}

    def verify(state: TicketState) -> TicketState:
        category = state["classification"].category
        checks = verification.verify(
            state["draft"],
            category,
            drafting.TEMPLATES[category].required_slots,
            _text(state),
            state["extraction"].language,
            state["evidence"],
            deps.llm,
        )
        passed = all(c.passed for c in checks)
        return {"checks": checks, "retries": state["retries"] + (0 if passed else 1)}

    def after_verify(state: TicketState) -> str:
        if all(c.passed for c in state["checks"]):
            return "review"
        return "hold" if state["retries"] > deps.max_retries else "draft"

    def hold(state: TicketState) -> TicketState:
        return {"status": TicketStatus.ON_HOLD}

    # 상담원 검토: 여기서 멈추고(PostgreSQL 체크포인트) 버튼 값이 오면 이어서 돈다 (CSA-25).
    def ready(state: TicketState) -> TicketState:
        return {"status": TicketStatus.READY_FOR_REVIEW}

    def review(state: TicketState) -> TicketState:
        payload = interrupt(
            {
                "ticket_id": state["ticket_id"],
                "pending": state["pending"],
                "status": state["status"],
            }
        )
        return {"review": ReviewIn.model_validate(payload)}

    def after_review(state: TicketState) -> str:
        action = state["review"].action
        if action == ReviewAction.REWRITE:
            return "draft"
        if action == ReviewAction.INFO_REQUEST:
            return "info_request"
        if action == ReviewAction.ESCALATE:
            return "escalate"
        return "finish"

    def rewrite_reset(state: TicketState) -> TicketState:
        return {"retries": 0, "checks": [], "review_rounds": state["review_rounds"] + 1}

    def escalate(state: TicketState) -> TicketState:
        # TODO(CSA-25): 이관 알림(Slack), SLA 감시 작업에 이관 건 표시
        target = state["review"].escalate_to or state["rules"].escalate_to
        return {
            "status": TicketStatus.ESCALATED,
            "escalated_to": target or state["rules"].assigned_dept,
        }

    def finish(state: TicketState) -> TicketState:
        review = state["review"]
        if review.action == ReviewAction.REJECT:
            return {"status": TicketStatus.REJECTED}
        if state["pending"] == "info_request":
            # 요청문 발송 → 고객 회신 대기 (SLA 시계 정지). 회신이 오면 ① 접수에서 재개.
            sent = review.edited_text or state["info_request"]
            return {"status": TicketStatus.WAITING_CUSTOMER, "info_request": sent}
        reply = review.edited_text if review.action == ReviewAction.EDIT_APPROVE else None
        return {"status": TicketStatus.APPROVED, "final_reply": reply or state["draft"].text}

    g = StateGraph(TicketState)
    for name, fn in [
        ("intake", intake),
        ("classify", classify),
        ("extract", extract),
        ("retrieve", retrieve),
        ("rules", rules),
        ("human_queue", human_queue),
        ("info_request", info_request),
        ("evidence", evidence),
        ("draft", draft),
        ("verify", verify),
        ("hold", hold),
        ("ready", ready),
        ("review", review),
        ("rewrite_reset", rewrite_reset),
        ("escalate", escalate),
        ("finish", finish),
    ]:
        g.add_node(name, fn)

    g.add_edge(START, "intake")
    for branch in ("classify", "extract", "retrieve"):  # N-01 병렬
        g.add_edge("intake", branch)
    g.add_edge(["classify", "extract", "retrieve"], "rules")
    g.add_conditional_edges(
        "rules",
        lambda s: s["route"],
        {Route.HUMAN: "human_queue", Route.INFO_REQUEST: "info_request", Route.DRAFT: "evidence"},
    )
    g.add_edge("human_queue", END)
    g.add_edge("info_request", "ready")
    g.add_edge("evidence", "draft")
    g.add_edge("draft", "verify")
    g.add_conditional_edges(
        "verify", after_verify, {"review": "ready", "draft": "draft", "hold": "hold"}
    )
    g.add_edge("ready", "review")
    g.add_edge("hold", "review")
    g.add_conditional_edges(
        "review",
        after_review,
        {
            "draft": "rewrite_reset",
            "info_request": "info_request",
            "escalate": "escalate",
            "finish": "finish",
        },
    )
    g.add_edge("rewrite_reset", "draft")
    g.add_edge("escalate", END)
    g.add_edge("finish", END)

    # TODO(CSA-24): DATABASE_URL이 있으면 langgraph-checkpoint-postgres의 PostgresSaver로 바꾼다.
    return g.compile(checkpointer=checkpointer or MemorySaver(serde=checkpoint_serde()))
