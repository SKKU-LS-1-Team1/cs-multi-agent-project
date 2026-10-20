# 문의 처리 그래프 조립 (CSA-21 · 담당 김동규 · Sprint 1)
#
# 슈퍼바이저 = 코드가 순서를 정한 LangGraph StateGraph(TicketState). LLM이 다음 단계를 고르지
# 않는다. 노드 함수는 짧게: 에이전트 함수를 부르고 바꾼 키만 돌려준다.
#
#   START → ① intake ─┬─ ② classify → ③ extract ─┬→ ⑤ rules → ⑥ 분기 ─┬ human → END (사람 큐)
#                     └─ ④ retrieve ──────────────┘                   ├ info_request → ⑦ → ready
#                                                                      ├ draft → ⑧ evidence → ⑨ → ⑩
#                                                                      └ analysis_pending → END
#   ⑩ verify ─┬ 통과 → ready → review
#             ├ 실패 · 재시도 남음 → ⑨ draft (실패 사유를 fix_notes 로)
#             └ 실패 · 재시도 초과 → hold(ON_HOLD) → review
#   review (interrupt: 상담원 버튼 대기) ─┬ approve / edit_approve / reject → finish → END
#                                     ├ rewrite → ⑨ draft (상담원 피드백, 재시도 0으로)
#                                     ├ info_request → ⑦ → ready → review
#                                     └ escalate → escalate(상태·부서 변경) → END
#
# - 에이전트 함수는 GraphDeps 로 받는다. 아직 구현 안 된 자리는 graph/defaults.py 임시 구현.
#   담당자가 agents/*.py 를 만들면 GraphDeps 기본값만 바꾼다.
# - ③ 추출은 ② 분류 결과(category)를 받아 필요한 항목을 찾으므로 분류 다음에 돈다.
# - 분석 실패(AnalysisError: Jev·Gemini 모두 실패 등)는 거짓 결과로 메우지 않는다.
#   안전 신호가 잡혔으면 사람 큐로, 아니면 ANALYSIS_PENDING(분석 대기)으로 멈추고
#   TicketService.retry_pending() 이 다시 돌린다. 원인은 analysis_error 에 남는다.
# - review 노드는 interrupt 만 한다. interrupt 앞에서 상태를 바꾸면 재개 때 노드가 다시 실행되므로
#   상태 표시는 ready / hold 노드에서 한다.
#   API(POST /api/tickets/{id}/action)가 Command(resume=ReviewIn.model_dump(mode="json"))로 잇는다.
# - 체크포인터: 개발은 InMemorySaver, 운영은 PostgresSaver (langgraph-checkpoint-postgres, CSA-24).
#   상태에 든 pydantic 모델·Enum 은 serializer() 에 등록해야 체크포인트에서 그대로 복원된다.
#
# TODO(CSA-21): 고객 회신이 오면 ① 접수에서 같은 thread_id 로 재개 (thread_ref 로 기존 티켓 찾기,
#   재문의 +1). 고객 회신 채널(CSA-32·39)이 생기면 붙인다.
# 참고: 에이전트_구조_제안.md 2장, 관리자_대시보드_AI기능_구조검토.md 4장
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from cs_agent import domain, schemas
from cs_agent.agents import analysis, retrieval
from cs_agent.agents.analysis import AnalysisError
from cs_agent.config import get_settings
from cs_agent.domain import ReviewAction, Route, TicketStatus, Urgency
from cs_agent.graph import defaults
from cs_agent.graph.state import TicketState
from cs_agent.llm.router import LLMRouter
from cs_agent.rules.engine import apply_rules
from cs_agent.rules.tables import RefTables, load_tables
from cs_agent.schemas import ReviewIn


@dataclass
class GraphDeps:
    llm: LLMRouter
    tables: RefTables = field(default_factory=load_tables)
    docs: Any = None  # Retriever (CSA-28)
    cases: Any = None  # Retriever (CSA-28)
    max_retries: int = field(default_factory=lambda: get_settings().max_verify_retries)
    # 에이전트 함수 (모양은 agents/*.py "만들 것" 주석)
    classify: Callable = analysis.classify
    extract: Callable = analysis.extract
    first_pass: Callable = retrieval.first_pass
    finalize_evidence: Callable = retrieval.finalize_evidence
    write_draft: Callable = defaults.write_draft  # TODO(CSA-29): agents.drafting.write_draft
    verify: Callable = defaults.verify  # TODO(CSA-31): agents.verification.verify
    write_info_request: Callable = defaults.write_info_request  # TODO(CSA-27)


def serializer() -> JsonPlusSerializer:
    """체크포인트에 넣는 우리 모델·Enum 을 등록한 serializer."""
    allowed = [
        (mod.__name__, name)
        for mod in (schemas, domain)
        for name, obj in vars(mod).items()
        if isinstance(obj, type) and obj.__module__ == mod.__name__
    ]
    return JsonPlusSerializer(allowed_msgpack_modules=allowed)


def _inquiry_text(state: TicketState) -> str:
    inquiry = state["inquiry"]
    return f"{inquiry.subject}\n{inquiry.body}".strip()


def _language(state: TicketState) -> str:
    extraction = state.get("extraction")
    return (extraction and extraction.language) or state["inquiry"].language or "en"


def _review(state: TicketState) -> ReviewIn | None:
    return state.get("review")


def build_ticket_graph(deps: GraphDeps, checkpointer: Any | None = None):
    # ① ~ ⑤ ----------------------------------------------------------------------------
    def intake(state: TicketState) -> dict:
        return {
            "status": TicketStatus.NEW,
            "retries": 0,
            "review_rounds": 0,
            "fix_notes": [],
            "classification": None,
            "extraction": None,
            "analysis_error": None,
        }

    def classify(state: TicketState) -> dict:
        try:
            return {"classification": deps.classify(state["inquiry"], deps.llm)}
        except AnalysisError as e:
            return {"analysis_error": str(e)}

    def extract(state: TicketState) -> dict:
        # 분류가 실패해도 추출은 돈다: 안전 신호는 유형 없이도 사람 큐로 보내야 한다
        classification = state.get("classification")
        try:
            result = deps.extract(
                state["inquiry"],
                deps.tables,
                llm=deps.llm,
                category=classification.category if classification else None,
            )
        except AnalysisError as e:
            return {"analysis_error": state.get("analysis_error") or str(e)}
        return {"extraction": result}

    def retrieve(state: TicketState) -> dict:
        return {"candidates": deps.first_pass(deps.docs, deps.cases, _inquiry_text(state))}

    def rules(state: TicketState) -> dict:
        extraction = state.get("extraction")
        if extraction and extraction.urgency == Urgency.SAFETY and not state.get("classification"):
            return {"rules": None, "route": Route.HUMAN}  # 유형 없이 사람 큐 (규칙은 상담원이)
        if state.get("analysis_error"):
            return {"rules": None, "route": None}
        result = apply_rules(
            state["classification"], extraction, state["inquiry"].customer_tier, deps.tables
        )
        if extraction.urgency == Urgency.SAFETY:
            route = Route.HUMAN
        elif result.missing_blocking:
            route = Route.INFO_REQUEST
        else:
            route = Route.DRAFT
        return {"rules": result, "route": route}

    def human(state: TicketState) -> dict:
        return {"status": TicketStatus.HUMAN_QUEUE}

    def analysis_pending(state: TicketState) -> dict:
        return {"status": TicketStatus.ANALYSIS_PENDING}

    # ⑦ ⑧ ⑨ ⑩ --------------------------------------------------------------------------
    def info_request(state: TicketState) -> dict:
        review = _review(state)
        if review and review.action == ReviewAction.INFO_REQUEST and review.info_items:
            missing = review.info_items
        else:
            missing = state["rules"].missing_blocking or state["rules"].missing_info
        text = deps.write_info_request(missing, _language(state), _inquiry_text(state), deps.llm)
        return {"info_request": text, "pending": "info_request"}

    def evidence(state: TicketState) -> dict:
        return {
            "evidence": deps.finalize_evidence(
                state.get("candidates", []),
                state["extraction"],
                category=state["classification"].category,
            )
        }

    def draft(state: TicketState) -> dict:
        review = _review(state)
        feedback = review.feedback if review and review.action == ReviewAction.REWRITE else None
        result = deps.write_draft(
            state["classification"].category,
            state["extraction"],
            state.get("evidence", []),
            _inquiry_text(state),
            deps.llm,
            fix_notes=state.get("fix_notes") or None,
            reviewer_feedback=feedback,
        )
        # 점검 실패 사유(fix_notes)를 받아 다시 쓰는 경우만 재시도로 센다
        retries = state.get("retries", 0) + (1 if state.get("fix_notes") else 0)
        return {"draft": result, "pending": "draft", "retries": retries}

    def verify(state: TicketState) -> dict:
        checks = deps.verify(
            state["draft"],
            state["classification"].category,
            (),  # TODO(CSA-29): drafting.TEMPLATES[category].required_slots
            _inquiry_text(state),
            _language(state),
            state.get("evidence", []),
            deps.llm,
        )
        return {"checks": checks, "fix_notes": [c.reason or c.name for c in checks if not c.passed]}

    def after_verify(state: TicketState) -> str:
        if not state.get("fix_notes"):
            return "ready"
        return "draft" if state.get("retries", 0) < deps.max_retries else "hold"

    # 상담원 검토 ----------------------------------------------------------------------
    def ready(state: TicketState) -> dict:
        return {"status": TicketStatus.READY_FOR_REVIEW}

    def hold(state: TicketState) -> dict:
        return {"status": TicketStatus.ON_HOLD}

    def review(state: TicketState) -> dict:
        value = interrupt(
            {
                "ticket_id": state["ticket_id"],
                "pending": state.get("pending"),
                "status": state.get("status"),
            }
        )
        return {"review": ReviewIn.model_validate(value)}

    def after_review(state: TicketState) -> str:
        action = state["review"].action
        return {
            ReviewAction.REWRITE: "rewrite",
            ReviewAction.INFO_REQUEST: "info_request",
            ReviewAction.ESCALATE: "escalate",
        }.get(action, "finish")

    def rewrite(state: TicketState) -> dict:
        return {
            "retries": 0,
            "fix_notes": [],
            "review_rounds": state.get("review_rounds", 0) + 1,
        }

    def finish(state: TicketState) -> dict:
        review = state["review"]
        if review.action == ReviewAction.REJECT:
            return {"status": TicketStatus.REJECTED, "final_reply": None}
        if state.get("pending") == "info_request":
            text = review.edited_text or state.get("info_request")
            return {"status": TicketStatus.WAITING_CUSTOMER, "final_reply": text}
        text = review.edited_text if review.action == ReviewAction.EDIT_APPROVE else None
        return {
            "status": TicketStatus.APPROVED,
            "final_reply": text or (state.get("draft") and state["draft"].text),
        }

    def escalate(state: TicketState) -> dict:
        review = state["review"]
        return {
            "status": TicketStatus.ESCALATED,
            "escalated_to": review.escalate_to
            or state["rules"].escalate_to
            or state["rules"].assigned_dept,
        }

    g = StateGraph(TicketState)
    for name, fn in [
        ("intake", intake),
        ("classify", classify),
        ("extract", extract),
        ("retrieve", retrieve),
        ("rules", rules),
        ("human", human),
        ("analysis_pending", analysis_pending),
        ("info_request", info_request),
        ("evidence", evidence),
        ("draft", draft),
        ("verify", verify),
        ("ready", ready),
        ("hold", hold),
        ("review", review),
        ("rewrite", rewrite),
        ("finish", finish),
        ("escalate", escalate),
    ]:
        g.add_node(name, fn)

    g.add_edge(START, "intake")
    g.add_edge("intake", "classify")
    g.add_edge("intake", "retrieve")  # ④ 는 ②③ 과 병렬
    g.add_edge("classify", "extract")
    g.add_edge(["extract", "retrieve"], "rules")
    g.add_conditional_edges(
        "rules",
        lambda s: s.get("route") or "analysis_pending",
        {
            Route.HUMAN: "human",
            Route.INFO_REQUEST: "info_request",
            Route.DRAFT: "evidence",
            "analysis_pending": "analysis_pending",
        },
    )
    g.add_edge("human", END)
    g.add_edge("analysis_pending", END)
    g.add_edge("info_request", "ready")
    g.add_edge("evidence", "draft")
    g.add_edge("draft", "verify")
    g.add_conditional_edges("verify", after_verify, ["ready", "draft", "hold"])
    g.add_edge("ready", "review")
    g.add_edge("hold", "review")
    g.add_conditional_edges(
        "review", after_review, ["rewrite", "info_request", "escalate", "finish"]
    )
    g.add_edge("rewrite", "draft")
    g.add_edge("finish", END)
    g.add_edge("escalate", END)

    return g.compile(checkpointer=checkpointer or InMemorySaver(serde=serializer()))
