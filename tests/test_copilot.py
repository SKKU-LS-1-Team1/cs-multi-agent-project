"""관리자 판단 보조: 근거, 요청 선택, 최신성, 업무 흐름 보존."""

import json
from copy import deepcopy
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from stubs import ANALYSIS
from test_db import TEST_DATABASE_URL, _db_service, needs_db
from test_db import db as db

from cs_agent.agents import copilot
from cs_agent.agents.case_patterns import assign_pattern
from cs_agent.config import Settings
from cs_agent.llm.clients import Judgement
from cs_agent.llm.router import LLMRouter
from cs_agent.main import create_app
from cs_agent.rules.engine import apply_rules
from cs_agent.rules.tables import load_tables
from cs_agent.schemas import Classification, Evidence, Extraction, InquiryIn

INQUIRY = {
    "channel": "email",
    "language": "en",
    "category": "TECH_SPEC",
    "subject": "TRF-OIL-1000",
    "body": "Please confirm its dimensions.",
    "provided_fields": {"application": "substation"},
}


def state():
    inquiry = InquiryIn(**INQUIRY)
    extraction = Extraction(
        product_family="DRIVE",
        product_code="INV-LSLV0075-S100",
        error_code="E.OC",
        serial_no="SN-42",
        field_values={"quantity": "2"},
        unconfirmed_fields={"current_fw": "withdrawn"},
    )
    classification = Classification(category="DEFECT")
    rules = apply_rules(classification, extraction, "STANDARD", load_tables())
    rules.required_info = ["serial_no", "quantity", "current_fw", "photos"]
    return {
        "inquiry": inquiry,
        "extraction": extraction,
        "classification": classification,
        "rules": rules,
        "status": "ON_HOLD",
        "customer_revision": 1,
        "evidence": [
            Evidence(source="cases", doc_id="CASE-1", text="S100 tripped on acceleration.")
        ],
    }


def statement(text="치수를 확인해 달라는 문의입니다.", source="customer:0", quote=None):
    return {
        "text": text,
        "references": [
            {
                "source_id": source,
                "quote": quote or "Please confirm its dimensions.",
            }
        ],
    }


def reading():
    return {"request": statement(), "confirmed": [], "unresolved": [], "cases": []}


class Models:
    enabled = True

    def __init__(self, result=None, verdict="yes"):
        self.result = result or reading()
        self.verdict = verdict
        self.calls = 0
        self.invalidated = []

    def write(self, task, prompt):
        self.calls += 1
        return json.dumps(self.result)

    def judge(self, task, prompt, options):
        return Judgement(self.verdict, 1, "test-judge")

    def invalidate_write(self, task, prompt):
        self.invalidated.append(task)


def test_plan_excludes_confirmed_from_requests_and_separates_optional():
    plan = {r["field"]: r for r in copilot.request_plan(state(), load_tables())}
    assert plan["serial_no"]["status"] == "confirmed"
    assert plan["quantity"]["value"] == "2"
    assert plan["current_fw"]["status"] == "clarify"
    assert plan["photos"]["status"] == "missing"
    assert not any(r["origin"] == "recommended" for r in plan.values())
    preparing = state()
    preparing["escalation_request"] = {"to_dept": "QA_CLAIM", "text": "Investigate E.OC"}
    plan = copilot.request_plan(preparing, load_tables())
    assert any(r["origin"] == "recommended" and not r["blocking"] for r in plan)


def test_current_withdrawals_override_stale_provided_fields():
    s = state()
    s["inquiry"].provided_fields = {"serial_no": "OLD", "current_fw": "1.0"}
    s["extraction"].unconfirmed_fields["serial_no"] = "withdrawn"
    plan = {r["field"]: r for r in copilot.request_plan(s, load_tables())}
    assert plan["serial_no"]["status"] == "clarify"
    assert "current_fw" not in copilot.fields_of(s)


@pytest.mark.parametrize("change", ["reply", "field", "review", "specialist", "evidence"])
def test_context_invalidates_old_reading(change):
    s = state()
    s["copilot_insight"] = copilot.generate(s, load_tables(), Models())
    assert copilot.view(s, load_tables())["reading"]
    if change == "reply":
        s["customer_messages"] = [{"body": "Withdraw the previous request."}]
    elif change == "field":
        s["extraction"].field_values["quantity"] = "3"
    elif change == "review":
        s["information_review"] = {"checked_at": "2026-10-31", "reviewer": "Kim"}
    elif change == "specialist":
        s["specialist_revision"] = 1
    else:
        s["evidence"] = []
    assert copilot.view(s, load_tables())["reading"] is None


def test_changes_are_actual_values_not_ai_generated():
    s = state()
    s["copilot_insight"] = copilot.generate(s, load_tables(), Models())
    s["extraction"].field_values["quantity"] = "3"
    new = copilot.generate(s, load_tables(), Models())
    assert [(r["field"], r["before"], r["after"]) for r in new["changes"]] == [
        ("quantity", "2", "3")
    ]


@pytest.mark.parametrize("bad", ["quote", "source", "field", "case", "comparison"])
def test_invented_evidence_and_one_sided_comparisons_are_rejected(bad):
    result = reading()
    if bad == "quote":
        result["request"]["references"][0]["quote"] = "not in the inquiry"
    elif bad == "source":
        result["request"]["references"][0]["source_id"] = "unknown"
    elif bad == "field":
        result["request_reasons"] = [{**statement(), "field": "serial_no"}]
    else:
        result["cases"] = [
            {
                "case_id": "cases:CASE-1#" if bad == "comparison" else "invented",
                "matches": [statement()],
                "use_limit": statement(),
            }
        ]
    models = Models(result)
    with pytest.raises(ValueError):
        copilot.generate(state(), load_tables(), models)
    assert models.invalidated == ["admin_copilot"]


def test_supported_case_comparison_requires_both_current_and_case_sources():
    s = state()
    comparison = statement("가속 중 트립은 공통이나 원인은 미확인입니다.")
    comparison["references"].append(
        {"source_id": "cases:CASE-1#", "quote": "S100 tripped on acceleration."}
    )
    result = reading()
    result["cases"] = [
        {
            "case_id": "cases:CASE-1#",
            "matches": [comparison],
            "use_limit": statement(
                "점검 참고이며 동일 원인으로 확정할 수 없습니다.",
                "cases:CASE-1#",
                "S100 tripped on acceleration.",
            ),
        }
    ]
    assert copilot.generate(s, load_tables(), Models(result))["reading"]["cases"]
    # 문자열 인용을 통과해도 의미가 지지되지 않으면 모델 검증이 차단한다.
    with pytest.raises(ValueError):
        copilot.generate(s, load_tables(), Models(result, verdict="no"))


def test_fake_and_capacity_fail_without_affecting_state(monkeypatch):
    s = state()
    before = deepcopy(s)
    with pytest.raises(ValueError):
        copilot.generate(s, load_tables(), SimpleNamespace(enabled=False))
    monkeypatch.setattr(copilot, "_CAPACITY", SimpleNamespace(acquire=lambda **_: False))
    with pytest.raises(ValueError):
        copilot.generate(s, load_tables(), Models())
    assert s == before


def test_timeout_never_returns_partial_reading(monkeypatch):
    class Future:
        def add_done_callback(self, callback):
            callback(self)

        def result(self, timeout):
            assert timeout == 35
            raise TimeoutError

    monkeypatch.setattr(copilot, "_POOL", SimpleNamespace(submit=lambda *a: Future()))
    with pytest.raises(ValueError, match="기존 업무"):
        copilot.generate(state(), load_tables(), Models())


@pytest.fixture
def client():
    app = create_app(
        llm=LLMRouter(Settings(_env_file=None)),
        agents=ANALYSIS,
        storage="memory",
        retrievers=(None, None),
    )
    with TestClient(app) as c:
        yield c


def stub_generation(monkeypatch, callback=None):
    original = copilot.generate

    def generate(s, tables, llm):
        result = original(s, tables, Models())
        if callback:
            callback()
        return result

    monkeypatch.setattr(copilot, "generate", generate)


def test_api_saves_reuses_and_keeps_graph_at_review(client, monkeypatch):
    stub_generation(monkeypatch)
    row = client.post("/api/tickets", json=INQUIRY).json()
    tid = row["ticket_id"]
    service = client.app.state.tickets
    before = service._state(tid)
    response = client.post(f"/api/tickets/{tid}/copilot")
    assert response.status_code == 200, response.text
    assert response.json()["reading"]["request"]["text"]
    after = service._state(tid)
    assert after.next == before.next == ("review",)
    assert after.values["status"] == before.values["status"]
    assert after.values["draft"] == before.values["draft"]
    monkeypatch.setattr(copilot, "generate", lambda *a: pytest.fail("should reuse saved result"))
    assert client.post(f"/api/tickets/{tid}/copilot").json() == response.json()
    assert client.get(f"/api/tickets/{tid}").json()["copilot"] == response.json()


def test_stale_generation_cannot_replace_latest_state(client, monkeypatch):
    tid = client.post("/api/tickets", json=INQUIRY).json()["ticket_id"]
    service = client.app.state.tickets
    stub_generation(
        monkeypatch,
        lambda: service.graph.update_state(
            service._config(tid), {"customer_revision": 10}, as_node="ready"
        ),
    )
    response = client.post(f"/api/tickets/{tid}/copilot")
    assert response.status_code == 409
    assert not service._state(tid).values.get("copilot_insight")
    assert service._state(tid).values["customer_revision"] == 10


def test_failed_ai_summary_does_not_block_existing_review(client):
    tid = client.post("/api/tickets", json=INQUIRY).json()["ticket_id"]
    assert client.post(f"/api/tickets/{tid}/copilot").status_code == 409
    assert (
        client.post(f"/api/tickets/{tid}/action", json={"action": "approve"}).json()["status"]
        == "APPROVED"
    )


def test_request_selection_rejects_stale_and_confirmed_fields(client):
    row = client.post("/api/tickets", json=INQUIRY).json()
    url = f"/api/tickets/{row['ticket_id']}/action"
    plan = row["copilot"]
    for key, items in [
        ("stale", ["serial_no"]),
        (plan["context_key"], ["application"]),
        (plan["context_key"], []),
    ]:
        response = client.post(
            url, json={"action": "info_request", "info_plan_key": key, "info_items": items}
        )
        assert response.status_code == 409, response.text


def test_only_selected_missing_field_reaches_request_writer(client):
    body = {**INQUIRY, "category": "DEFECT", "subject": "S100 E.OC", "body": "S100 trips with E.OC"}
    row = client.post("/api/tickets", json=body).json()
    items = [r["field"] for r in row["copilot"]["request_plan"] if r["status"] != "confirmed"]
    assert len(items) > 1
    response = client.post(
        f"/api/tickets/{row['ticket_id']}/action",
        json={
            "action": "info_request",
            "info_plan_key": row["copilot"]["context_key"],
            "info_items": items[:1],
        },
    )
    assert response.status_code == 200, response.text
    service = client.app.state.tickets
    assert service._state(row["ticket_id"]).values["review"].info_items == items[:1]
    assert response.json()["info_request"]


def test_mail_copilot_does_not_register_ticket(client, monkeypatch):
    # 메일 원문을 동적으로 인용하는 대역: 실제 읽기/쓰기 서비스 경로는 유지.
    def generate(s, tables, llm):
        key, data = copilot.context(s, tables)
        return {"context_key": key, "sources": data["sources"], "reading": reading(), "changes": []}

    monkeypatch.setattr(copilot, "generate", generate)
    mail = client.get("/api/mail").json()[0]
    result = client.post(f"/api/mail/{mail['mail_id']}/copilot")
    assert result.status_code == 200, result.text
    monkeypatch.setattr(copilot, "generate", lambda *a: pytest.fail("should use cache"))
    assert client.post(f"/api/mail/{mail['mail_id']}/copilot").json() == result.json()
    assert client.get("/api/tickets").json() == []


def test_korean_resolutions_do_not_collapse_into_same_pattern():
    assert assign_pattern("DRIVE", "단자 풀림")
    assert assign_pattern("DRIVE", "S100 단자 풀림") != assign_pattern("DRIVE", "S100 냉각팬 고장")


# 실제 PostgreSQL 체크포인트에서 신규 dict가 재시작 후 복원되는지 확인한다.


@needs_db
def test_reading_survives_postgres_restart_without_changing_review_node(db, monkeypatch):
    from cs_agent.graph.builder import postgres_checkpointer
    from cs_agent.schemas import ReviewIn

    stub_generation(monkeypatch)
    _, session = db
    with postgres_checkpointer(TEST_DATABASE_URL) as saver:
        service = _db_service(session, saver)
        tid = service.submit(InquiryIn(**INQUIRY)).ticket_id
        expected = service.refresh_copilot(tid, Models())
    with postgres_checkpointer(TEST_DATABASE_URL) as saver:
        service = _db_service(session, saver)
        assert service.get(tid).copilot == expected
        assert service._state(tid).next == ("review",)
        assert service.act(tid, ReviewIn(action="approve")).status == "APPROVED"


def test_corrected_scalar_overrides_original_form_value():
    s = state()
    s["inquiry"].provided_fields = {"product_model": "iS7", "serial_no": "OLD"}
    values = copilot.fields_of(s)
    assert values["product_model"] == "INV-LSLV0075-S100"
    assert values["serial_no"] == "SN-42"


def test_specialist_requested_fields_use_only_fresh_reply_reading():
    from cs_agent.agents.specialist_followup import source_version

    s = state()
    requests = [
        {
            "request_id": "R1",
            "to_dept": "QA_CLAIM",
            "reply": {
                "reply_id": "REP1",
                "text": "Please send the logs and serial number.",
            },
        }
    ]
    s["specialist_requests"] = requests
    s["specialist_followup"] = {
        "source_version": source_version(s, requests),
        "reading": {
            "requested_fields": [
                {"field": "logs", "evidence": "Please send the logs and serial number."},
                {"field": "serial_no", "evidence": "Please send the logs and serial number."},
            ],
            "needs_review": False,
        },
    }
    plan = {r["field"]: r for r in copilot.request_plan(s, load_tables())}
    assert plan["logs"]["origin"] == "specialist"
    assert plan["serial_no"]["status"] == "confirmed"
    s["customer_revision"] += 1
    stale = {r["field"]: r for r in copilot.request_plan(s, load_tables())}
    assert "logs" not in stale
    assert (
        copilot.context(s, load_tables())[1]["current_state"]["specialist_followup"]["reading"]
        is None
    )


def test_rewrite_stays_information_request_and_keeps_selected_items(client):
    body = {**INQUIRY, "category": "DEFECT", "subject": "S100 E.OC", "body": "S100 trips with E.OC"}
    row = client.post("/api/tickets", json=body).json()
    tid = row["ticket_id"]
    selected = [r["field"] for r in row["copilot"]["request_plan"] if r["status"] != "confirmed"][
        :1
    ]
    first = client.post(
        f"/api/tickets/{tid}/action",
        json={
            "action": "info_request",
            "info_plan_key": row["copilot"]["context_key"],
            "info_items": selected,
        },
    )
    assert first.status_code == 200
    rewritten = client.post(
        f"/api/tickets/{tid}/action", json={"action": "rewrite", "feedback": "Be concise"}
    )
    assert rewritten.status_code == 200, rewritten.text
    assert rewritten.json()["info_request"]
    assert rewritten.json()["draft"] is None
    saved = client.app.state.tickets._state(tid).values
    assert saved["info_request_fields"] == selected
    assert saved["pending"] == "info_request"


def test_rewrite_cannot_request_fields_confirmed_after_original_draft(client):
    body = {**INQUIRY, "category": "DEFECT", "subject": "S100 E.OC", "body": "S100 trips with E.OC"}
    row = client.post("/api/tickets", json=body).json()
    tid = row["ticket_id"]
    response = client.post(
        f"/api/tickets/{tid}/action",
        json={
            "action": "info_request",
            "info_plan_key": row["copilot"]["context_key"],
            "info_items": ["photos"],
        },
    )
    assert response.status_code == 200
    service = client.app.state.tickets
    extraction = service._state(tid).values["extraction"].model_copy(deep=True)
    extraction.field_values["photos"] = "attached"
    service.graph.update_state(service._config(tid), {"extraction": extraction}, as_node="ready")
    response = client.post(
        f"/api/tickets/{tid}/action", json={"action": "rewrite", "feedback": "shorter"}
    )
    assert response.status_code == 409
    assert "모두 확인" in response.json()["detail"]


@pytest.mark.parametrize(
    ("updates", "mode"),
    [
        ({"status": "WAITING_CUSTOMER", "pending": "info_request"}, "wait_customer"),
        ({"status": "APPROVED"}, "closed"),
        ({"status": "ANALYSIS_PENDING"}, "analysis_pending"),
        ({"status": "HUMAN_QUEUE"}, "manual_review"),
        ({"pending": "info_request"}, "customer_request"),
        ({"escalation_request": {"text": "Investigate E.OC"}}, "specialist_prepare"),
        (
            {"escalation_request": {"text": "Investigate E.OC"}, "pending": "info_request"},
            "specialist_prepare",
        ),
        ({"specialist_requests": [{"to_dept": "QA_CLAIM", "reply": None}]}, "wait_specialist"),
        (
            {
                "specialist_requests": [
                    {
                        "to_dept": "QA_CLAIM",
                        "reply": {"reply_id": "R", "text": "Inspection completed"},
                    }
                ]
            },
            "specialist_review",
        ),
    ],
)
def test_workflow_respects_actual_action_and_waiting_before_missing_fields(updates, mode):
    s = {**state(), **updates}
    payload = copilot.context(s, load_tables())[1]
    assert payload["workflow"]["mode"] == mode
    if mode not in {"customer_request", "specialist_prepare"}:
        assert payload["workflow"]["request_fields"] == []
    if mode == "customer_request":
        assert "load_type" not in payload["workflow"]["request_fields"]


def test_answer_review_is_not_referral_just_because_routing_has_a_department():
    s = state()
    s["rules"].required_info = ["serial_no", "quantity"]
    assert s["rules"].escalate_to
    payload = copilot.context(s, load_tables())[1]
    assert payload["workflow"]["mode"] == "customer_answer"
    assert not payload["workflow"]["request_fields"]
    assert not any(r["origin"] == "recommended" for r in payload["request_plan"])


def test_selected_optional_request_survives_rewrite_without_suggesting_other_materials():
    s = state()
    s.update(pending="info_request", info_request_fields=["cable_length"])
    payload = copilot.context(s, load_tables())[1]
    assert payload["workflow"]["request_fields"] == ["cable_length"]
    assert "load_type" not in {r["field"] for r in payload["request_plan"]}


def test_waiting_reading_cannot_propose_request_reasons():
    s = {**state(), "status": "WAITING_CUSTOMER"}
    payload = copilot.context(s, load_tables())[1]
    result = {**reading(), "request_reasons": [{**statement(), "field": "photos"}]}
    with pytest.raises(ValueError, match="Unsupported requested field"):
        copilot.validate(copilot.Reading.model_validate(result), payload)


@pytest.mark.parametrize(
    "updates",
    [
        {"pending": "info_request"},
        {"escalation_request": {"text": "Investigate E.OC"}},
        {"status": "WAITING_CUSTOMER"},
        {"info_request_fields": ["photos"]},
    ],
)
def test_action_changes_invalidate_previous_ai_reason(updates):
    s = state()
    s["copilot_insight"] = copilot.generate(s, load_tables(), Models())
    s.update(updates)
    assert copilot.view(s, load_tables())["reading"] is None


def test_automatic_request_checklist_matches_actual_blocking_fields():
    s = state()
    s["pending"] = "info_request"
    s["rules"].missing_blocking = ["photos"]
    s["rules"].missing_info = ["photos", "current_fw"]
    payload = copilot.context(s, load_tables())[1]
    assert payload["workflow"]["request_fields"] == ["photos"]
    s["review"] = {"action": "info_request", "info_items": ["current_fw"]}
    assert copilot.context(s, load_tables())[1]["workflow"]["request_fields"] == ["current_fw"]
