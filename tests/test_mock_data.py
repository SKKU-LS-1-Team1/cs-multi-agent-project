from datetime import UTC, datetime, timedelta

import pytest
import stubs
from fastapi.testclient import TestClient

from cs_agent.config import Settings
from cs_agent.domain import Category
from cs_agent.graph.builder import GraphDeps, build_ticket_graph
from cs_agent.llm.router import LLMRouter
from cs_agent.main import create_app
from cs_agent.pipeline import mock_data
from cs_agent.schemas import CheckResult, Draft, InquiryIn
from cs_agent.services.tickets import TicketService

NOW = datetime(2026, 10, 20, 9, 0, tzinfo=UTC)


def _expected_category(inquiry, llm):
    """시나리오 기대 유형을 돌려주는 분류 대역 (분류 품질은 실제 LLM 평가에서 본다)"""
    item = next(i for i in mock_data.demo_scenarios(NOW) if i["inquiry"].body == inquiry.body)
    return stubs.classify(inquiry.model_copy(update={"category": item["expect"]["category"]}), llm)


AGENTS = {
    "classify": _expected_category,
    "extract": stubs.extract,
    "write_draft": lambda *a, **k: Draft(text="draft", model="stub"),
    # 답변이 대역이라 자동 점검도 대역으로 (점검은 tests/test_verification.py 에서 본다)
    "verify": lambda *a, **k: [CheckResult(name="stub", passed=True)],
    "write_info_request": lambda missing, *a: f"please send {', '.join(missing)}",
}


@pytest.mark.parametrize("item", mock_data.demo_scenarios(NOW), ids=lambda i: i["id"])
def test_demo_scenario_reaches_expected_route(item):
    service = TicketService(
        build_ticket_graph(GraphDeps(llm=LLMRouter(Settings(_env_file=None)), **AGENTS))
    )

    ticket = service.submit(item["inquiry"])

    assert (ticket.route, ticket.status) == (item["expect"]["route"], item["expect"]["status"])


def test_samples_come_only_from_train_without_answers():
    items = mock_data.sample_inquiries(per_category=2, seed=1, now=NOW)

    assert len(items) == 2 * len(Category)
    assert {i["expect"]["category"] for i in items} == set(Category)
    sources = {i["source"] for i in items}
    import csv

    split = {
        r["ticket_id"]: r["data_split"]
        for r in csv.DictReader(
            (Settings(_env_file=None).raw_data_dir / "tickets.csv").open(encoding="utf-8-sig")
        )
    }
    assert {split[s] for s in sources} == {"train"}  # valid·test 는 쓰지 않는다
    for item in items:
        inquiry = item["inquiry"]
        assert (inquiry.category, inquiry.product_code, inquiry.provided_fields) == (None, None, {})
        assert NOW - timedelta(hours=72) <= inquiry.received_at <= NOW


def test_same_seed_same_samples():
    first = mock_data.sample_inquiries(per_category=1, seed=3, now=NOW)
    again = mock_data.sample_inquiries(per_category=1, seed=3, now=NOW)

    assert [i["id"] for i in first] == [i["id"] for i in again]


def test_json_round_trips_to_inquiry():
    rows = mock_data.to_json(mock_data.build(per_category=1))

    assert len(rows) == 4 + len(Category)
    assert all(InquiryIn.model_validate(r["inquiry"]) for r in rows)


def test_post_all_submits_through_api():
    items = mock_data.demo_scenarios()
    app = create_app(
        llm=LLMRouter(Settings(_env_file=None)),
        agents=AGENTS,
        storage="memory",
        retrievers=(None, None),
    )
    with TestClient(app) as client:
        results = mock_data.post_all(items, client=client)
        stored = len(client.app.state.tickets.records.ticket_ids())

    assert stored == len(items)
    assert [r["status"] for r in results] == [i["expect"]["status"] for i in items]
