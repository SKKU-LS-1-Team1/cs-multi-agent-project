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
#   review (interrupt: 상담원 버튼 대기) ─┬ approve / edit_approve → finish(고객 언어 번역) → END
#                                     │                          └ 번역 실패 → hold → review
#                                     │   (추가정보 요청문도 같다: 번역 3번 실패 → hold, CSA-27)
#                                     ├ reject → finish → END
#                                     ├ rewrite → ⑨ draft (상담원 피드백, 재시도 0으로)
#                                     ├ info_request → ⑦ → ready → review
#                                     └ escalate → escalate(상태·부서 변경) → END
#
# - 에이전트 함수는 GraphDeps 로 받는다 (기본값은 agents/*.py 실제 구현).
#   담당자가 agents/*.py 를 만들면 GraphDeps 기본값만 바꾼다.
# - ③ 추출은 ② 분류 결과(category)를 받아 필요한 항목을 찾으므로 분류 다음에 돈다.
# - 분석 실패(AnalysisError: Jev·Gemini 모두 실패 등)는 거짓 결과로 메우지 않는다.
#   안전 신호가 잡혔으면 사람 큐로, 아니면 ANALYSIS_PENDING(분석 대기)으로 멈추고
#   TicketService.retry_pending() 이 다시 돌린다. 원인은 analysis_error 에 남는다.
# - review 노드는 interrupt 만 한다. interrupt 앞에서 상태를 바꾸면 재개 때 노드가 다시 실행되므로
#   상태 표시는 ready / hold 노드에서 한다.
#   API(POST /api/tickets/{id}/action)가 Command(resume=ReviewIn.model_dump(mode="json"))로 잇는다.
# - 체크포인터: 개발은 InMemorySaver, 운영은 PostgresSaver (postgres_checkpointer(), CSA-24).
#   상태에 든 pydantic 모델·Enum 은 serializer() 에 등록해야 체크포인트에서 그대로 복원된다.
# - 고객 회신: 같은 thread_id 에 새 입력(원문 + 회신, followups +1)을 넣으면 ① 접수부터 다시 돈다
#   (services/tickets.py reply). 검토 대기 중이었으면 그 검토는 버린다. ① 이 지난 판단·답변·상담원
#   입력을 지워야 이전 상담원 피드백이 새 답변에 섞이지 않는다.
# 참고: 에이전트_구조_제안.md 2장, 관리자_대시보드_AI기능_구조검토.md 4장
import hashlib
import json
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

import cs_agent.agents.translation as translation
from cs_agent import domain, schemas
from cs_agent.agents import analysis, customer_qc, drafting, escalation, retrieval, verification
from cs_agent.agents import info_request as info_request_agent
from cs_agent.agents.analysis import AnalysisError
from cs_agent.agents.drafting import DraftingError, TranslationError
from cs_agent.config import get_settings
from cs_agent.domain import ReviewAction, Route, TicketStatus, Urgency
from cs_agent.graph.state import TicketState
from cs_agent.llm.router import LLMRouter
from cs_agent.rules.engine import apply_rules
from cs_agent.rules.tables import RefTables, load_tables
from cs_agent.schemas import CheckResult, ReviewIn
from cs_agent.services.reply_preview import review_text, valid_preview


@dataclass
class GraphDeps:
    llm: LLMRouter
    tables: RefTables = field(default_factory=load_tables)
    docs: Any = None  # Retriever (CSA-28)
    cases: Any = None  # Retriever (CSA-28)
    graph: Any = None  # 지식 그래프 (CSA-71, agents/knowledge_graph.py). None 이면 패턴 DB
    max_retries: int = field(default_factory=lambda: get_settings().max_verify_retries)
    # 에이전트 함수 (모양은 agents/*.py "만들 것" 주석)
    translate: Callable = translation.translate_to_korean
    classify: Callable = analysis.classify
    extract: Callable = analysis.extract
    first_pass: Callable = retrieval.first_pass
    finalize_evidence: Callable = retrieval.finalize_evidence
    write_draft: Callable = drafting.write_draft
    verify: Callable = verification.verify
    check_customer_qc: Callable = customer_qc.check_final
    write_info_request: Callable = info_request_agent.write_info_request
    localize_info_request: Callable = info_request_agent.localize_request  # 보낼 때 고객 언어로
    translate_reply: Callable = drafting.translate_reply
    write_escalation_request: Callable = escalation.write_escalation_request


def serializer() -> JsonPlusSerializer:
    """체크포인트에 넣는 우리 모델·Enum 을 등록한 serializer."""
    allowed = [
        (mod.__name__, name)
        for mod in (schemas, domain)
        for name, obj in vars(mod).items()
        if isinstance(obj, type) and obj.__module__ == mod.__name__
    ]
    return JsonPlusSerializer(allowed_msgpack_modules=allowed)


@contextmanager
def postgres_checkpointer(database_url: str) -> Iterator[Any]:
    """PostgresSaver (연결 풀). 체크포인트 테이블이 없으면 만든다. 앱이 끝날 때 풀을 닫는다."""
    from langgraph.checkpoint.postgres import PostgresSaver
    from psycopg.rows import dict_row
    from psycopg_pool import ConnectionPool
    from sqlalchemy.engine import make_url

    # SQLAlchemy 주소(postgresql+psycopg://)를 psycopg 주소로
    conninfo = make_url(database_url).set(drivername="postgresql")
    kwargs = {"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row}
    with ConnectionPool(
        conninfo.render_as_string(hide_password=False), kwargs=kwargs, open=True
    ) as pool:
        saver = PostgresSaver(pool, serde=serializer())
        saver.setup()
        yield saver


def _inquiry_text(state: TicketState) -> str:
    inquiry = state["inquiry"]
    return f"{inquiry.subject}\n{inquiry.body}".strip()


def _analysis_context(state: TicketState) -> tuple[schemas.InquiryIn, list[analysis.ChatMessage]]:
    """표시용 합친 본문과 분리해 분석에는 최신 발언과 과거 발언을 각각 전달한다."""
    inquiry = state["inquiry"]
    messages = state.get("customer_messages", [])
    if not messages:
        return inquiry, []
    latest = messages[-1]
    return (
        inquiry.model_copy(update={"body": latest["body"]}),
        [analysis.ChatMessage(role="user", content=message["body"]) for message in messages[:-1]],
    )


def _language(state: TicketState) -> str:
    extraction = state.get("extraction")
    return state["inquiry"].language or (extraction and extraction.language) or "en"


def _review(state: TicketState) -> ReviewIn | None:
    return state.get("review")


def build_ticket_graph(deps: GraphDeps, checkpointer: Any | None = None):
    # ① ~ ⑤ ----------------------------------------------------------------------------
    def intake(state: TicketState) -> dict:
        # 고객 회신·분석 대기 재시도로 다시 돌 때 지난 판단·답변·상담원 입력을 지운다
        return {
            "status": TicketStatus.NEW,
            "manual_reply": False,
            "reply_preview": None,
            "retries": 0,
            "review_rounds": 0,
            "fix_notes": [],
            "classification": None,
            "extraction": None,
            "analysis_error": None,
            "draft": None,
            "draft_customer_revision": state.get("customer_revision", 0),
            "draft_information_reviewed_at": None,
            "information_review_refresh": False,
            "drafting_error": None,
            "info_request": None,
            "escalation_request": None,
            "checks": [],
            "evidence": [],
            "review": None,
            "final_reply": None,
            "approved_reply": None,
            "approval_text": None,
            "approval_error": None,
            "customer_qc": None,
            "approval_checks_key": None,
            "approval_review": None,
            "approval_cited": None,
            "translation_error": None,
            "escalated_to": None,
            # 상담원용 원문 번역은 배경에서 시작, 검토·끝 직전에 받는다 (CSA-57, 아래 _translation)
            "translation_job": _start_translation(state),
        }

    def _start_translation(state: TicketState) -> str:
        inquiry = state["inquiry"]
        return translation.start_job(
            inquiry.body,
            inquiry.language,
            state.get("translation_parts", []),
            deps.translate,
            deps.llm,
        )

    def _restart_translation(state: TicketState) -> dict:
        """번역이 비어 있으면 다시 시작 (상담원 재작성·추가정보 요청 때). 성공한 구간은 재사용."""
        if state.get("body_ko") or state.get("translation_job"):
            return {}
        return {"translation_job": _start_translation(state)}

    def _translation(state: TicketState) -> dict:
        """배경 번역을 받는다. 남은 시간만 기다리고, 실패·시간 초과면 번역 없이 진행."""
        if not state.get("translation_job"):
            return {}
        result = translation.collect_job(state["translation_job"])
        if result is None:
            return {"translation_job": None}
        body_ko, parts = result
        return {"body_ko": body_ko, "translation_parts": parts, "translation_job": None}

    def classify(state: TicketState) -> dict:
        inquiry = state["inquiry"]
        options = {}
        if deps.classify is analysis.classify:
            inquiry, transcript = _analysis_context(state)
            options["transcript"] = transcript
            if messages := state.get("customer_messages"):
                options["category_is_current"] = messages[-1].get("category") is not None
        try:
            return {"classification": deps.classify(inquiry, deps.llm, **options)}
        except AnalysisError as e:
            return {"analysis_error": str(e)}

    def extract(state: TicketState) -> dict:
        # 분류가 실패해도 추출은 돈다: 안전 신호는 유형 없이도 사람 큐로 보내야 한다
        classification = state.get("classification")
        inquiry = state["inquiry"]
        options = {}
        if deps.extract is analysis.extract:
            inquiry, transcript = _analysis_context(state)
            options["transcript"] = transcript
            if classification:
                options["secondary_category"] = classification.secondary_category
            if len(messages := state.get("customer_messages", [])) > 1:
                options["current_provided_fields"] = messages[-1].get("provided_fields", {})
                options["current_product_code"] = messages[-1].get("product_code")
        try:
            result = deps.extract(
                inquiry,
                deps.tables,
                llm=deps.llm,
                category=classification.category if classification else None,
                **options,
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
        return {"status": TicketStatus.HUMAN_QUEUE, **_translation(state)}

    def analysis_pending(state: TicketState) -> dict:
        return {"status": TicketStatus.ANALYSIS_PENDING, **_translation(state)}

    # ⑦ ⑧ ⑨ ⑩ --------------------------------------------------------------------------
    def info_request(state: TicketState) -> dict:
        review = _review(state)
        if review and review.action == ReviewAction.INFO_REQUEST and review.info_items:
            missing = review.info_items
        else:
            missing = state["rules"].missing_blocking or state["rules"].missing_info
        from cs_agent.rules.investigation import investigation_info

        advisory = investigation_info(state, deps.tables)
        if advisory and not (review and review.info_items):
            missing = list(dict.fromkeys([*missing, *advisory["missing_fields"]]))
        # 고객 답변과 같이 영어로 검토하고, 승인한 문장만 finish에서 고객 언어로 바꾼다.
        text = deps.write_info_request(missing, "en", _inquiry_text(state), deps.llm)
        return {
            "info_request": text,
            "draft": None,
            "draft_customer_revision": state.get("customer_revision", 0),
            "draft_information_reviewed_at": (state.get("information_review") or {}).get(
                "checked_at"
            ),
            "pending": "info_request",
            "approved_reply": None,
            "approval_text": None,
            "approval_error": None,
            "customer_qc": None,
            "approval_checks_key": None,
            "approval_review": None,
            "approval_cited": None,
            "translation_error": None,
            "final_reply": None,
            **_restart_translation(state),
        }

    def evidence(state: TicketState) -> dict:
        candidates = state.get("candidates", [])
        if state.get("information_review_refresh"):
            # 담당자가 확정한 값으로 검색도 갱신해 이전 제품의 검색 결과를 재사용하지 않는다.
            fields = state["extraction"].field_values
            confirmed = "\n".join(f"{name}: {value}" for name, value in sorted(fields.items()))
            query = f"{_inquiry_text(state)}\nConfirmed fields:\n{confirmed}"
            candidates = deps.first_pass(deps.docs, deps.cases, query)
        # 지식 그래프는 문의 글로 증상을 비교한다 (켜져 있을 때만 넘긴다 — 주입한 대역의 규격 유지)
        graph = {}
        if deps.graph is not None:
            graph = {"graph": deps.graph, "query": _inquiry_text(state)}
        return {
            "candidates": candidates,
            "information_review_refresh": False,
            "evidence": deps.finalize_evidence(
                candidates,
                state["extraction"],
                category=state["classification"].category,
                **graph,
            ),
        }

    def draft(state: TicketState) -> dict:
        review = _review(state)
        feedback = review.feedback if review and review.action == ReviewAction.REWRITE else None
        from cs_agent.agents.specialist_followup import current_followup

        followup = current_followup(state, state.get("specialist_requests", []))
        confirmation = followup.get("confirmation") if followup else None
        if confirmation:
            feedback = "\n".join(
                filter(
                    None,
                    [
                        feedback,
                        "Staff-confirmed specialist finding (preserve scope and conditions): "
                        + confirmation["finding"]["evidence"],
                    ],
                )
            )
        options = {"fix_notes": state.get("fix_notes") or None, "reviewer_feedback": feedback}
        evidence = state.get("evidence", [])
        if deps.write_draft is drafting.write_draft:
            # 주입한 기존 호출 대역의 규격은 유지하고 실제 작성기에 조회 문맥을 전달한다.
            options.update(
                tables=deps.tables,
                secondary_category=state["classification"].secondary_category,
                specialist_replies=state.get("specialist_replies", []),
            )
            # 재작성 때 이전 회신 근거를 누적하지 않고 최신 저장값으로 다시 구성한다.
            evidence = [e for e in evidence if e.source != "specialist"]
            evidence += drafting.specialist_evidence(state.get("specialist_replies", []))
            evidence = drafting.prepare_evidence(
                state["classification"].category,
                state["extraction"],
                evidence,
                secondary_category=state["classification"].secondary_category,
                tables=deps.tables,
                raw_dir=deps.llm.settings.raw_data_dir,
            )
        try:
            result = deps.write_draft(
                state["classification"].category,
                state["extraction"],
                evidence,
                _inquiry_text(state),
                deps.llm,
                **options,
            )
        except DraftingError as error:
            return {
                "draft": None,
                "info_request": None,
                "pending": "draft",
                "drafting_error": str(error),
                "evidence": evidence,
            }
        # 점검 실패 사유(fix_notes)를 받아 다시 쓰는 경우만 재시도로 센다
        retries = state.get("retries", 0) + (1 if state.get("fix_notes") else 0)
        return {
            "draft": result,
            "info_request": None,
            "draft_specialist_revision": state.get("specialist_revision", 0),
            "draft_customer_revision": state.get("customer_revision", 0),
            "draft_information_reviewed_at": (state.get("information_review") or {}).get(
                "checked_at"
            ),
            "pending": "draft",
            "retries": retries,
            "drafting_error": None,
            "evidence": evidence,
        }

    def checked_key(state: TicketState, candidate: schemas.Draft, language: str) -> str:
        """검사한 본문뿐 아니라 근거·고객 문의·적용 조건까지 같을 때만 결과를 재사용한다."""
        payload = {
            "text": candidate.text,
            "slots": candidate.slots,
            "cited": candidate.cited,
            "language": language,
            "classification": state["classification"].model_dump(mode="json")
            if state.get("classification")
            else None,
            "inquiry": state["inquiry"].model_dump(mode="json"),
            "evidence": [e.model_dump(mode="json") for e in state.get("evidence", [])],
            "specialist_revision": state.get("specialist_revision", 0),
            "customer_revision": state.get("customer_revision", 0),
            "information_review": state.get("information_review"),
            "extraction": state["extraction"].model_dump(mode="json")
            if state.get("extraction")
            else None,
            "manual_reply": state.get("manual_reply", False),
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()

    def check_candidate(state: TicketState, candidate: schemas.Draft, language: str) -> list:
        classification = state.get("classification")
        secondary = classification.secondary_category if classification else None
        if deps.verify is verification.verify and secondary:
            secondary_check = verification.check_banned(candidate, secondary, language)
            if not secondary_check.passed:
                return [secondary_check.model_copy(update={"name": "banned_secondary"})]
        checks = deps.verify(
            candidate,
            classification.category if classification else None,
            ()
            if state.get("manual_reply")
            else drafting.required_slots(classification.category, secondary),
            _inquiry_text(state),
            language,
            state.get("evidence", []),
            deps.llm,
        )
        if state.get("manual_reply") and not classification:
            checks.append(
                CheckResult(
                    name="analysis_unavailable",
                    passed=False,
                    reason=(
                        "분류 미확인: 유형별 점검을 완료하지 못했습니다. 담당자 확인이 필요합니다."
                    ),
                )
            )
        return checks

    def verify(state: TicketState) -> dict:
        if error := state.get("drafting_error"):
            return {
                "checks": [CheckResult(name="draft_input_or_output", passed=False, reason=error)],
                "fix_notes": [error],
                "approval_checks_key": None,
                "approval_review": None,
                "approval_cited": None,
            }
        candidate = state["draft"]
        language = candidate.slots.get("draft_language") or _language(state)
        checks = check_candidate(state, candidate, language)
        return {
            "checks": checks,
            "fix_notes": [c.reason or c.name for c in checks if not c.passed],
            "approval_checks_key": checked_key(state, candidate, language),
        }

    def after_verify(state: TicketState) -> str:
        if state.get("drafting_error"):
            return "hold"  # 원천값 누락·호출 장애는 모델 재작성으로 사실을 만들어 채우지 않는다.
        if not state.get("fix_notes"):
            return "ready"
        return "draft" if state.get("retries", 0) < deps.max_retries else "hold"

    # 상담원 검토 ----------------------------------------------------------------------
    def ready(state: TicketState) -> dict:
        return {"status": TicketStatus.READY_FOR_REVIEW, **_translation(state)}

    def hold(state: TicketState) -> dict:
        return {"status": TicketStatus.ON_HOLD, **_translation(state)}

    def review(state: TicketState) -> dict:
        value = interrupt(
            {
                "ticket_id": state["ticket_id"],
                "pending": state.get("pending"),
                "status": state.get("status"),
            }
        )
        return {"review": ReviewIn.model_validate(value), "customer_qc": None}

    def after_review(state: TicketState) -> str:
        review = state["review"]
        action = review.action
        if action == ReviewAction.EDIT_APPROVE and not (review.edited_text or "").strip():
            return "hold"
        if (
            state.get("pending") == "draft"
            and not state.get("draft")
            and not state.get("approval_text")
            and not (state.get("translation_error") and state.get("approved_reply"))
        ):
            if action == ReviewAction.APPROVE:
                return "hold"
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
            "approved_reply": None,
            "approval_text": None,
            "approval_error": None,
            "customer_qc": None,
            "approval_checks_key": None,
            "approval_review": None,
            "approval_cited": None,
            "translation_error": None,
            "final_reply": None,
            **_restart_translation(state),
        }

    def history(state: TicketState, kind: str, **data) -> list[dict]:
        return [
            *state.get("processing_history", []),
            {
                "id": str(uuid4()),
                "kind": kind,
                "created_at": datetime.now(UTC).isoformat(),
                "actor": state["review"].reviewer,
                **data,
            },
        ]

    def sent_history(state: TicketState, text: str, final_reply: str, purpose: str) -> list[dict]:
        draft = state.get("draft")
        return history(
            state,
            "sent",
            text=final_reply,
            master_text=text,
            purpose=purpose,
            reply_language=_language(state),
            edited=state.get("manual_reply", False)
            or (
                text
                != (
                    state.get("info_request")
                    if purpose == "request"
                    else (drafting.customer_text(draft.text, draft.cited) if draft else "")
                )
            ),
        )

    def final_qc(state: TicketState, final_reply: str, text: str) -> dict:
        try:
            result = deps.check_customer_qc(
                final_reply,
                _language(state),
                deps.llm,
                restricted_context=customer_qc.restricted_sources(state.get("evidence", [])),
            )
        except Exception:
            result = customer_qc.error_result(final_reply)
        update = {"customer_qc": result.model_dump(mode="json")}
        if result.decision != "PASS":
            update.update(
                status=TicketStatus.ON_HOLD,
                final_reply=None,
                approved_reply=text,
                approval_text=text,
                translation_error=None,
                approval_error=result.message
                or "발송 전 QC에서 수정 또는 공개 범위 확인이 필요합니다.",
            )
        return update

    def finish(state: TicketState) -> dict:
        review = state["review"]
        if review.action == ReviewAction.REJECT:
            return {
                "status": TicketStatus.REJECTED,
                "processing_history": history(state, "rejected", text="문의 반려"),
                "final_reply": None,
                "approved_reply": None,
                "approval_text": None,
                "approval_error": None,
                "customer_qc": None,
                "approval_checks_key": None,
                "approval_review": None,
                "approval_cited": None,
                "translation_error": None,
            }
        preview_text = None
        if review.reply_preview_id:
            if not valid_preview(state, review_text(state, review), review.reply_preview_id):
                return {
                    "status": TicketStatus.ON_HOLD,
                    "final_reply": None,
                    "approval_error": (
                        "초안 또는 문의 정보가 변경되었습니다. 고객 언어로 다시 변환해 주세요"
                    ),
                }
            preview_text = state["reply_preview"]["final_text"]
        if state.get("pending") == "info_request":
            # 번역 실패로 보류된 뒤 다시 승인하면, 직전에 상담원이 수정 승인한 글을 그대로 쓴다
            if review.action == ReviewAction.EDIT_APPROVE and review.edited_text:
                text = review.edited_text
            elif (state.get("translation_error") or state.get("approval_error")) and state.get(
                "approved_reply"
            ):
                text = state["approved_reply"]
            else:
                text = state.get("info_request")
            # 승인한 요청문이 고객 언어가 아니면(영어 틀 문장 등) 발송 직전에 옮긴다 (CSA-27).
            # 3번 다 실패하면 보내지 않고 보류 → 상담원이 다시 승인하면 다시 번역한다
            try:
                final_reply = (
                    preview_text
                    if preview_text is not None
                    else deps.localize_info_request(text, _language(state), deps.llm)
                )
            except info_request_agent.LocalizationError as error:
                return {
                    "status": TicketStatus.ON_HOLD,
                    "approved_reply": text,
                    "final_reply": None,
                    "translation_error": str(error),
                }
            qc = final_qc(state, final_reply, text)
            if qc.get("approval_error"):
                return qc
            return {
                **qc,
                "approval_error": None,
                "status": TicketStatus.WAITING_CUSTOMER,
                "processing_history": sent_history(state, text, final_reply, "request"),
                "final_reply": final_reply,
                "approved_reply": text,
                "translation_error": None,
            }
        # 번역 재시도에서도 직전에 담당자가 수정 승인한 원문을 보존한다.
        if review.action == ReviewAction.EDIT_APPROVE:
            text = review.edited_text
        elif state.get("approval_text"):
            text = state["approval_text"]
        elif state.get("translation_error"):
            text = state.get("approved_reply")
        else:
            text = None
        text = text or (state.get("draft") and state["draft"].text) or ""
        draft = state.get("draft")
        allowed = [drafting._ref(e) for e in state.get("evidence", [])]
        citation_error = None
        try:
            cited = drafting._citations(text, allowed)
            # New drafts keep references separately; old checkpoints may still have them inline.
            # Only unchanged wording can retain the original draft's source attribution.
            if draft and drafting.customer_text(text, allowed) == drafting.customer_text(
                draft.text, allowed
            ):
                cited = list(
                    dict.fromkeys(
                        [
                            *cited,
                            *drafting._citations(draft.text, allowed),
                            *(ref for ref in draft.cited if ref in allowed),
                        ]
                    )
                )
        except DraftingError as error:
            citation_error = str(error)
            cited = []
        text = drafting.customer_text(text, allowed)
        source_language = (
            draft.slots.get("draft_language") or _language(state)
            if draft
            else drafting.REVIEW_LANGUAGE
        )
        # 담당자 수정본도 번역·발송 전에 정확히 그 본문을 검사한다. 원 AI 초안은 보존한다.
        language = (
            _language(state)
            if info_request_agent.in_language(text, _language(state))
            else source_language
        )
        candidate = (draft or schemas.Draft(text="")).model_copy(
            update={"text": text, "cited": cited}
        )
        if not draft or text != drafting.customer_text(draft.text, allowed):
            candidate = candidate.model_copy(update={"model": "staff_review"})
        checks = state.get("checks", [])
        key = checked_key(state, candidate, language)
        already_checked = key == state.get("approval_checks_key") and bool(checks)
        acknowledged = bool(review.acknowledged_failures and review.reviewer.strip())
        transient_failure = any(
            not check.passed
            and (
                check.name == "approval_verification_error"
                or (check.name == "grounding" and "근거 검증 호출 실패" in (check.reason or ""))
            )
            for check in checks
        )
        if not already_checked or (transient_failure and not acknowledged):
            try:
                checks = (
                    [CheckResult(name="citations", passed=False, reason=citation_error)]
                    if citation_error
                    else check_candidate(state, candidate, language)
                )
            except Exception:
                checks = [
                    CheckResult(
                        name="approval_verification_error",
                        passed=False,
                        reason="최종 답변 점검 실패: 재점검하거나 담당자가 확인해 주세요.",
                    )
                ]
        approval_review = (
            dict(state.get("approval_review") or {}) if text == state.get("approval_text") else {}
        )
        current_review = review.model_dump(mode="json", exclude_none=True)
        if (
            approval_review.get("action") == ReviewAction.EDIT_APPROVE
            and review.action == ReviewAction.APPROVE
        ):
            current_review.pop("action", None)
        approval_review.update({k: v for k, v in current_review.items() if v != ""})
        validation = {
            "checks": checks,
            "approval_text": text,
            "approval_cited": candidate.cited,
            "approval_checks_key": key,
            "approval_error": None,
            "customer_qc": None,
            "approval_review": approval_review,
        }
        if not checks or any(not c.passed for c in checks):
            # 이전 초안에 누른 체크박스로 새 수정본 실패를 묵시적으로 승인하지 않는다.
            if not (already_checked and acknowledged):
                return {
                    **validation,
                    "status": TicketStatus.ON_HOLD,
                    "approved_reply": None,
                    "final_reply": None,
                    "translation_error": None,
                    "approval_error": "최종 점검 실패: 수정 또는 실패 항목 확인 후 승인해 주세요.",
                }
        try:
            # 상담원이 고객 언어로 직접 고쳐 승인했으면(그 언어로 확인될 때만) 번역하지 않는다.
            # 영어 초안 기준(en)으로 다시 옮기면 같은 글이 돌아와 번역 실패로 보류됐다
            if preview_text is not None:
                final_reply = preview_text
            elif info_request_agent.in_language(text, _language(state)):
                final_reply = text
            else:
                final_reply = deps.translate_reply(
                    text, source_language, _language(state), deps.llm
                )
        except TranslationError as error:
            return {
                **validation,
                "status": TicketStatus.ON_HOLD,
                "approved_reply": text,
                "final_reply": None,
                "translation_error": str(error),
            }
        qc = final_qc(state, final_reply, text)
        if qc.get("approval_error"):
            return {**validation, **qc}
        return {
            **validation,
            **qc,
            "status": TicketStatus.APPROVED,
            "processing_history": sent_history(state, text, final_reply, "answer"),
            "approved_reply": text,
            "final_reply": final_reply,
            "translation_error": None,
        }

    def escalate(state: TicketState) -> dict:
        review = state["review"]
        request = state.get("escalation_request")
        rules = state.get("rules")
        target = review.escalate_to or (request.to_dept if request else None)
        target = target or (rules.escalate_to or rules.assigned_dept if rules else None)
        return {
            "status": TicketStatus.ESCALATED,
            "translation_error": None,
            "final_reply": None,
            "escalated_to": target,
            "escalation_request": request.model_copy(update={"text": review.edited_text})
            if request and review.edited_text is not None
            else request,
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
        "review", after_review, ["rewrite", "info_request", "escalate", "finish", "hold"]
    )
    g.add_edge("rewrite", "draft")
    g.add_conditional_edges(
        "finish",
        lambda s: "hold" if s.get("translation_error") or s.get("approval_error") else END,
        ["hold", END],
    )
    g.add_edge("escalate", END)

    return g.compile(checkpointer=checkpointer or InMemorySaver(serde=serializer()))
