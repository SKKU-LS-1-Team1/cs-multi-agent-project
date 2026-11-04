"""이관 권장: 규칙·AI 판단·근거 인용. 권장만 하고 문의 처리 흐름은 바꾸지 않는다."""

from types import SimpleNamespace as NS

from fastapi.testclient import TestClient
from test_api import ANALYSIS, INQUIRY
from test_api import client as client

from cs_agent.agents.escalation_advice import assess, known_faults, safe_assess
from cs_agent.config import Settings
from cs_agent.domain import Category
from cs_agent.llm.router import LLMRouter
from cs_agent.main import create_app
from cs_agent.rules.tables import load_tables

BODY = "We tried to update the unit but the update failed halfway."


def state(category=Category.FW_UPDATE, priority="P3", **extraction):
    return {
        "inquiry": NS(subject="Update failed", body=BODY),
        "classification": NS(category=category),
        "extraction": NS(
            **{"product_code": "P", "error_code": None, "return_defect": None, **extraction}
        ),
        "rules": NS(routing_rule_id="RT-ALL", priority=priority, escalate_to="RND_FW"),
    }


def router(answer="yes", confidence=0.9, written=None):
    calls = []

    def judge(task, prompt, options):
        calls.append(task)
        return NS(answer=answer, confidence=confidence, model="jev")

    def write(task, prompt):
        calls.append(task)
        if isinstance(written, Exception):
            raise written
        return written or '{"reason": "업데이트 실패 보고", "quote": "the update failed halfway"}'

    return NS(enabled=True, judge=judge, write=write, invalidate_write=lambda *a: None), calls


def tables():
    base = load_tables()
    row = {"rule_id": "RT-ALL", "escalation_condition": "업데이트 실패인 경우"}
    return NS(routing={"x": row}, escalation=[], faults=base.faults)


def test_documents_quotes_and_non_defect_returns_are_not_sent_to_ai():
    for item in (
        state(Category.MANUAL),
        state(Category.QUOTE),
        state(Category.RETURN, return_defect=False),
    ):
        llm, calls = router()
        assert assess(item, tables(), llm)["decision"] == "not_needed"
        assert calls == []


def test_p1_defect_is_recommended_by_rule_without_ai():
    llm, calls = router()
    advice = assess(state(Category.DEFECT, "P1"), tables(), llm)
    assert (advice["decision"], advice["source"], calls) == ("recommended", "rule", [])


def test_ai_recommends_only_with_confident_yes_and_a_real_customer_quote():
    llm, calls = router()
    advice = assess(state(), tables(), llm)
    assert (advice["decision"], advice["source"], advice["to_dept"]) == (
        "recommended",
        "ai",
        "RND_FW",
    )
    assert advice["quote"] == "the update failed halfway"
    assert calls == ["escalation_need", "escalation_advice"]


def test_no_or_low_confidence_does_not_recommend_or_write_a_reason():
    for answer, confidence in (("no", 0.99), ("yes", 0.79)):
        llm, calls = router(answer, confidence)
        assert assess(state(), tables(), llm)["decision"] == "not_needed"
        assert calls == ["escalation_need"]


def test_invented_quote_cancels_the_recommendation():
    llm, _ = router(written='{"reason": "x", "quote": "the unit is on fire"}')
    assert assess(state(), tables(), llm)["decision"] == "not_needed"


def test_reason_that_contradicts_the_decision_cancels_the_recommendation():
    reason = '{"reason": "조건에 해당하지 않습니다", "quote": "update failed"}'
    assert assess(state(), tables(), router(written=reason)[0])["decision"] == "not_needed"


def test_fenced_reason_is_accepted_and_failures_leave_the_decision_to_staff():
    fenced = '```json\n{"reason": "x", "quote": "update failed"}\n```'
    assert assess(state(), tables(), router(written=fenced)[0])["decision"] == "recommended"
    assert safe_assess(state(), tables(), router(written=ValueError("x"))[0]) is None
    assert safe_assess(state(), tables(), router(written="not json")[0]) is None


def test_ai_is_not_called_when_llm_is_off_or_there_is_no_target():
    llm, calls = router()
    llm.enabled = False
    assert assess(state(), tables(), llm) is None
    llm.enabled = True
    item = state()
    item["rules"].escalate_to = None
    assert assess(item, tables(), llm)["decision"] == "not_needed"
    assert calls == []


def test_known_faults_are_limited_to_the_product_and_reported_code():
    base = load_tables()
    extraction = NS(product_code="INV-LSLV0075-S100", error_code="E.OC")
    rows = known_faults(extraction, base)
    assert rows
    assert {r["error_code"] for r in rows} == {"E.OC"}
    assert known_faults(NS(product_code=None, error_code=None), base) == []


def test_advice_does_not_change_routing_and_is_exposed_on_the_ticket():
    advice = {"decision": "recommended", "source": "ai", "to_dept": "QA_CLAIM"}
    outs = []
    for agents in (ANALYSIS, {**ANALYSIS, "assess_escalation": lambda *a: advice}):
        app = create_app(
            llm=LLMRouter(Settings(_env_file=None)),
            agents=agents,
            storage="memory",
            retrievers=(None, None),
        )
        with TestClient(app) as c:
            outs.append(c.post("/api/tickets", json=INQUIRY).json())
    plain, advised = outs
    assert advised["escalation_advice"] == advice
    assert plain["escalation_advice"] != advice
    for key in ("status", "route", "assigned_dept", "priority"):
        assert advised[key] == plain[key]


def test_customer_reply_judges_again():
    seen = []

    def stub(state, tables, llm):
        seen.append(state["inquiry"].body)
        return None

    app = create_app(
        llm=LLMRouter(Settings(_env_file=None)),
        agents={**ANALYSIS, "assess_escalation": stub},
        storage="memory",
        retrievers=(None, None),
    )
    with TestClient(app) as c:
        first = {**INQUIRY, "thread_ref": "advice-thread"}
        c.post("/api/tickets", json=first)
        c.post("/api/tickets", json={**first, "body": "Here is the serial number SN-1."})
    assert len(seen) == 2
    assert "SN-1" in seen[1]


def test_ticket_without_advice_keeps_working(client):
    """배포 전에 들어온 문의는 판단 결과가 없다. 조회·검토가 그대로 돌아야 한다."""
    tid = client.post("/api/tickets", json=INQUIRY).json()["ticket_id"]
    service = client.app.state.tickets
    service.graph.update_state(service._config(tid), {"escalation_advice": None}, as_node="ready")
    out = client.get(f"/api/tickets/{tid}").json()
    assert out["escalation_advice"] is None
    acted = client.post(f"/api/tickets/{tid}/action", json={"action": "reject", "reviewer": "T"})
    assert acted.status_code == 200


def test_measurement_excludes_undecided_and_counts_precision_and_recall():
    from cs_agent.evaluation.escalation_advice import rows_of, summarize

    assert summarize([(True, True), (True, False), (False, True), (False, False)]) == {
        "n": 4,
        "actual_rate": 0.5,
        "advised_rate": 0.5,
        "precision": 0.5,
        "recall": 0.5,
    }
    rows = rows_of("train", 50)
    assert rows
    assert not {"IN_PROGRESS", "NEW", "WAITING_CUSTOMER"} & {r["status"] for r in rows}
