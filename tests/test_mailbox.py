# 업무 메일함 (CSA-74, services/mailbox.py · api/mail.py): 메일 → AI 분석 → 담당자 검토 → 티켓 등록
from collections import Counter
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from stubs import ANALYSIS

from cs_agent.config import Settings
from cs_agent.llm.router import LLMRouter
from cs_agent.main import create_app
from cs_agent.schemas import Classification
from cs_agent.services.mailbox import MAILS_PER_CATEGORY, load_mails

CALLS: Counter = Counter()


def classify(inquiry, llm, **kwargs):
    """메일은 유형이 없다: 담당자가 고르면 그 값, 아니면 AI 판단 대역(불량)."""
    CALLS["classify"] += 1
    if inquiry.category:
        return Classification(category=inquiry.category, confidence=1.0, model="customer")
    return Classification(category="DEFECT", confidence=0.9, model="stub")


def extract(inquiry, tables, **kwargs):
    CALLS["extract"] += 1
    return ANALYSIS["extract"](inquiry, tables, **kwargs)


@pytest.fixture
def client():
    CALLS.clear()
    agents = {**ANALYSIS, "classify": classify, "extract": extract}
    app = create_app(
        llm=LLMRouter(Settings(_env_file=None)),
        agents=agents,
        storage="memory",
        retrievers=(None, None),
    )
    with TestClient(app) as c:
        yield c


def test_mailbox_has_valid_email_inquiries_per_category_newest_first():
    now = datetime(2026, 10, 29, 9, 0, tzinfo=UTC)
    mails = load_mails(now=now)

    assert len(mails) == 10 * MAILS_PER_CATEGORY  # 유형 10개
    assert len({m.mail_id for m in mails}) == len(mails)
    assert all(m.received_at < now for m in mails)
    assert [m.received_at for m in mails] == sorted((m.received_at for m in mails), reverse=True)
    assert all(m.subject and m.body and m.sender for m in mails)


def test_analysis_sets_department_without_creating_a_ticket(client):
    mail = client.get("/api/mail").json()[0]
    assert mail["ticket_id"] is None and mail["analyzed"] is False

    result = client.post(f"/api/mail/{mail['mail_id']}/analyze").json()

    assert result["error"] is None
    assert result["classification"]["category"] == "DEFECT"
    assert result["rules"]["assigned_dept"] and result["rules"]["priority"]
    assert result["route"] in ("draft", "info_request", "human")
    assert (result["category_by"], result["product_by"]) == ("ai", "ai")
    assert client.get("/api/tickets").json() == []  # 분석만으로는 티켓이 생기지 않는다
    assert client.get(f"/api/mail/{mail['mail_id']}").json()["analyzed"] is True

    client.post(f"/api/mail/{mail['mail_id']}/analyze")  # 같은 값이면 캐시
    assert CALLS == {"classify": 1, "extract": 1}


def test_reviewer_choice_reruns_rules(client):
    mail_id = client.get("/api/mail").json()[0]["mail_id"]
    ai = client.post(f"/api/mail/{mail_id}/analyze").json()

    quote = client.post(f"/api/mail/{mail_id}/analyze", json={"category": "QUOTE"}).json()

    assert quote["classification"]["category"] == "QUOTE"
    assert quote["category_by"] == "reviewer"
    assert quote["rules"]["routing_rule_id"] != ai["rules"]["routing_rule_id"]


def test_register_creates_one_ticket_with_reviewed_category(client):
    mail_id = client.get("/api/mail").json()[0]["mail_id"]
    reviewed = client.post(f"/api/mail/{mail_id}/analyze", json={"category": "QUOTE"}).json()

    created = client.post(
        f"/api/mail/{mail_id}/register", json={"category": "QUOTE", "reviewer": "김동규"}
    )
    assert created.status_code == 201
    ticket = created.json()
    assert ticket["category"] == "QUOTE"
    assert ticket["assigned_dept"] == reviewed["rules"]["assigned_dept"]  # 검토한 부서 그대로
    assert ticket["inquiry"]["channel"] == "EMAIL"

    again = client.post(f"/api/mail/{mail_id}/register", json={"category": "QUOTE"}).json()
    assert again["ticket_id"] == ticket["ticket_id"]  # 두 번 눌러도 티켓은 하나
    assert [t["ticket_id"] for t in client.get("/api/tickets").json()] == [ticket["ticket_id"]]
    listed = {m["mail_id"]: m for m in client.get("/api/mail").json()}
    assert listed[mail_id]["ticket_id"] == ticket["ticket_id"]


def test_unknown_mail_is_404(client):
    assert client.post("/api/mail/MAIL-NOPE/analyze").status_code == 404
    assert client.get("/api/mail/MAIL-NOPE").status_code == 404
