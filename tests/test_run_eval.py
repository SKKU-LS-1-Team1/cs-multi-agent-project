import json
from types import SimpleNamespace

import pytest

from cs_agent.domain import ReviewAction, TicketStatus
from cs_agent.evaluation import run_eval
from cs_agent.evaluation.run_eval import (
    build_inquiry,
    build_result,
    demo_halves,
    mistakes,
    render_markdown,
    save,
    submit_all,
)

ROW = {
    "ticket_id": "CSV1-000123",
    "channel": "EMAIL",
    "customer_id": "CUST-0001",
    "customer_tier": "GOLD",
    "country": "DE",
    "language": "de",
    "inquiry_subject": "E.OC trip",
    "inquiry_body": "Our S100 trips with E.OC.",
    # 정답 열 — 입력에 들어가면 안 된다
    "product_code": "INV-LSLV0075-S100",
    "category_code": "DEFECT",
    "assigned_dept": "TS_DRIVE",
}


def _result(**overrides):
    row = {
        "gold_ticket_id": "G-1",
        "ticket_id": "T-1",
        "language": "en",
        "status": "READY_FOR_REVIEW",
        "gold_category": "DEFECT",
        "category": "DEFECT",
        "category_match": True,
        "gold_dept": "TS_LV",
        "assigned_dept": "TS_LV",
        "dept_match": True,
        "gold_priority": "P3",
        "priority": "P3",
        "priority_match": True,
        "priority_adjusted_by_agent": False,
        "gold_missing_info": [],
        "missing_info": [],
        "missing_info_match": True,
        "gold_missing_count": 0,
        "missing_found_count": 0,
        "gold_info_request_sent": False,
        "info_request_sent": False,
        "gold_reference_doc_id": "TG-X",
        "gold_reference_section": "3.1",
        "evidence_top3": ["TG-X#3.1"],
        "evidence_match": True,
        "review_action": None,
        "latency_s": 10.0,
        "error": None,
    }
    return row | overrides


def test_build_inquiry_sends_only_customer_fields() -> None:
    inquiry = build_inquiry(ROW, "eval-1")

    assert inquiry.thread_ref == "eval-1:CSV1-000123"  # eval_join.sql 연결 규칙
    assert (inquiry.channel, inquiry.customer_tier, inquiry.language) == ("EMAIL", "GOLD", "de")
    assert inquiry.subject == "E.OC trip" and inquiry.body.startswith("Our S100")
    assert inquiry.product_code is None and inquiry.category is None
    assert inquiry.provided_fields == {}


def test_build_inquiry_handles_missing_values() -> None:
    inquiry = build_inquiry({"ticket_id": "X", "inquiry_body": "b", "country": float("nan")}, "r")

    assert (inquiry.channel, inquiry.customer_tier, inquiry.country) == ("EMAIL", "STANDARD", None)


class FakeService:
    """submit → 상태, act/resolve 기록. 상태는 본문으로 정한다."""

    def __init__(self) -> None:
        self.acted: list[str] = []
        self.reviews: list = []
        self.resolved: list[str] = []
        self.count = 0

    def submit(self, inquiry):
        if inquiry.body == "boom":
            raise RuntimeError("graph failed")
        self.count += 1
        status = {
            "draft": TicketStatus.READY_FOR_REVIEW,
            "info": TicketStatus.READY_FOR_REVIEW,
            "human": TicketStatus.HUMAN_QUEUE,
        }[inquiry.body]
        draft = SimpleNamespace(text="AI 초안") if inquiry.body == "draft" else None
        return SimpleNamespace(
            ticket_id=f"T-{inquiry.body}-{self.count}", status=status, draft=draft
        )

    def act(self, ticket_id, review):
        self.acted.append(ticket_id)
        self.reviews.append(review)
        # 추가정보 요청문을 승인하면 고객 회신 대기
        status = TicketStatus.WAITING_CUSTOMER if "info" in ticket_id else TicketStatus.APPROVED
        return SimpleNamespace(status=status)

    def resolve(self, ticket_id):
        self.resolved.append(ticket_id)
        return SimpleNamespace(status=TicketStatus.RESOLVED)


def test_submit_all_records_latency_and_keeps_going_after_error() -> None:
    rows = [
        {"ticket_id": f"G-{i}", "inquiry_body": body}
        for i, body in enumerate(["draft", "boom", "human"])
    ]

    runs = submit_all(FakeService(), rows, "r")

    assert runs["G-0"]["ticket_id"] == "T-draft-1" and runs["G-0"]["latency_s"] >= 0
    assert runs["G-1"]["ticket_id"] is None and "graph failed" in runs["G-1"]["error"]
    assert runs["G-2"]["status"] == TicketStatus.HUMAN_QUEUE


def test_demo_resolves_only_sent_answers() -> None:
    service = FakeService()
    rows = [
        {"ticket_id": "G-0", "inquiry_body": "draft", "final_reply": "실제 회신"},
        {"ticket_id": "G-1", "inquiry_body": "info", "final_reply": "실제 회신"},
        {"ticket_id": "G-2", "inquiry_body": "human"},
    ]

    runs = submit_all(service, rows, "r", demo=True)

    assert service.acted == ["T-draft-1", "T-info-2"]  # 사람 큐는 건드리지 않는다
    # 답변 초안은 실제 회신으로 수정 승인 (CSA-15), 추가정보 요청문은 그대로 승인
    draft_review, info_review = service.reviews
    assert (draft_review.action, draft_review.edited_text) == (
        ReviewAction.EDIT_APPROVE,
        "실제 회신",
    )
    assert info_review.action == ReviewAction.APPROVE and info_review.edited_text is None
    assert "has_draft" not in runs["G-0"]  # 내부 표시는 결과에 남기지 않는다
    assert service.resolved == ["T-draft-1"]  # 추가정보 요청은 해결하지 않는다
    assert runs["G-0"]["status"] == TicketStatus.RESOLVED
    assert runs["G-1"]["status"] == TicketStatus.WAITING_CUSTOMER
    assert "demo_error" not in runs["G-1"]


def test_mistakes_attribute_owner_cards() -> None:
    rows = [
        _result(),  # 다 맞음
        _result(
            gold_ticket_id="G-2", category_match=False, category="TECH_SPEC", dept_match=False
        ),  # 유형이 틀려 부서도 틀림 → 둘 다 CSA-26
        _result(gold_ticket_id="G-3", dept_match=False, evidence_match=False),
        _result(
            gold_ticket_id="G-4",
            priority_match=False,
            priority_adjusted_by_agent=True,
            evidence_match=None,
        ),  # 상담원 조정·정답 근거 없음 → 틀린 것 아님
        _result(gold_ticket_id="G-5", ticket_id=None, error="RuntimeError: x"),
    ]

    by_id = {m["gold_ticket_id"]: m for m in mistakes(rows)}

    assert set(by_id) == {"G-2", "G-3", "G-5"}
    assert by_id["G-2"]["failed"] == ["category", "dept"] and by_id["G-2"]["owners"] == ["CSA-26"]
    assert by_id["G-3"]["owners"] == ["CSA-22", "CSA-28"]
    assert by_id["G-3"]["evidence"] == ["TG-X#3.1", ["TG-X#3.1"]]
    assert by_id["G-5"] == {
        "gold_ticket_id": "G-5",
        "failed": ["not_processed"],
        "owners": ["CSA-50"],
        "error": "RuntimeError: x",
    }


def test_demo_halves_compare_live_case_usage() -> None:
    rows = [_result(gold_ticket_id=f"G-{i}", ticket_id=f"T-{i}") for i in range(4)]

    halves = demo_halves(rows, {"T-2": 1, "T-3": 2}, ["G-0", "G-1", "G-2", "G-3"])

    assert halves["first_half"]["processed"] == 2
    assert halves["first_half"]["live_case_used"] == 0.0
    assert halves["second_half"]["live_case_used"] == 1.0


def test_result_is_saved_as_json_and_markdown(tmp_path, monkeypatch) -> None:
    rows = [_result(), _result(gold_ticket_id="G-2", language="de", category_match=False)]
    runs = {"G-1": {"error": None}, "G-2": {"error": None, "demo_error": "x"}}

    result = build_result("valid", "eval-1", rows, runs)
    path = save(result, tmp_path)

    saved = json.loads(path.read_text())
    assert path.name.startswith("eval_valid_") and path.suffix == ".json"
    assert saved["report"]["processed"] == 2 and saved["report"]["category_accuracy"] == 0.5
    assert set(saved["by_language"]) == {"de", "en"}
    assert saved["demo_errors"] == {"G-2": "x"}
    markdown = path.with_suffix(".md").read_text()
    assert "## 유형별" in markdown and "CSA-26: 1건" in markdown
    assert render_markdown(result) == markdown


def test_test_split_needs_final_flag() -> None:
    with pytest.raises(SystemExit, match="N-05"):
        run_eval.main(["--split", "test"])


def test_demo_without_gold_reply_approves_draft_as_is() -> None:
    service = FakeService()

    submit_all(service, [{"ticket_id": "G-0", "inquiry_body": "draft"}], "r", demo=True)

    assert service.reviews[0].action == ReviewAction.APPROVE


def test_demo_report_does_not_measure_k2() -> None:
    from cs_agent.evaluation.run_eval import build_result, demo_halves

    rows = [
        {"gold_ticket_id": f"G-{i}", "ticket_id": f"T-{i}", "gold_category": "TECH_SPEC",
         "review_action": "edit_approve", "dept_match": True}
        for i in range(4)
    ]  # fmt: skip
    halves = demo_halves(rows, {}, [f"G-{i}" for i in range(4)])
    assert halves["first_half"]["K2_approve_as_is"] is None
    result = build_result("valid", "r", rows, {}, demo=halves)
    assert result["report"]["K2_approve_as_is"] is None and "K2_note" in result["report"]
    plain = build_result("valid", "r", rows, {})
    assert plain["report"]["K2_approve_as_is"] == 0.0  # 시연이 아니면 그대로 잰다
