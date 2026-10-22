from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from stubs import ANALYSIS

from cs_agent.config import Settings
from cs_agent.llm.router import LLMRouter
from cs_agent.main import create_app
from cs_agent.services.assignment import (
    COLUMNS,
    Agent,
    assign,
    load_agents,
    reassign,
    suggest,
)

ROSTER = [
    Agent("A-2", "two", "TS_LV"),
    Agent("A-1", "one", "TS_LV", max_open=1),
    Agent("A-3", "off", "TS_LV", active=False),
    Agent("B-1", "mv", "TS_MV"),
]


# --- 명단 -------------------------------------------------------------------------------------


def test_repo_roster_is_valid_and_covers_every_dept() -> None:
    agents = load_agents()
    depts = {a.dept for a in agents}
    assert len(agents) == len({a.agent_id for a in agents})
    assert {"TS_LV", "TS_TRF", "FIELD_SVC", "CERT", "QA_CLAIM"} <= depts


def _csv(tmp_path: Path, *rows: str, header: str = ",".join(COLUMNS)) -> Path:
    path = tmp_path / "agents.csv"
    path.write_text("\n".join([header, *rows]) + "\n", encoding="utf-8")
    return path


@pytest.mark.parametrize(
    "row, message",
    [
        ("A-1,a,NOPE,Y,0", "없는 부서"),
        ("A-1,a,TS_LV,yes,0", "active"),
        ("A-1,a,TS_LV,Y,many", "max_open 은 정수"),
        ("A-1,a,TS_LV,Y,-1", "0 이상"),
        (",a,TS_LV,Y,0", "agent_id"),
    ],
)
def test_load_agents_rejects_bad_rows(tmp_path, row, message) -> None:
    with pytest.raises(ValueError, match=message):
        load_agents(_csv(tmp_path, row), depts={"TS_LV"})


def test_load_agents_rejects_duplicates_and_wrong_header(tmp_path) -> None:
    dup = _csv(tmp_path, "A-1,a,TS_LV,Y,0", "A-1,b,TS_LV,N,0")
    with pytest.raises(ValueError, match="겹친다"):
        load_agents(dup, depts={"TS_LV"})
    with pytest.raises(ValueError, match="열은"):
        load_agents(_csv(tmp_path, "A-1,a,TS_LV", header="agent_id,name,dept"), depts={"TS_LV"})


def test_load_agents_missing_file_is_empty(tmp_path) -> None:
    assert load_agents(tmp_path / "none.csv", depts=set()) == []


def test_load_agents_parses_values(tmp_path) -> None:
    path = _csv(tmp_path, "A-1, 상담원 ,TS_LV,N,5")
    assert load_agents(path, depts={"TS_LV"}) == [Agent("A-1", "상담원", "TS_LV", False, 5)]


# --- 배정 규칙 ---------------------------------------------------------------------------------


def test_assign_picks_least_loaded_active_agent_in_dept() -> None:
    assert assign("TS_LV", {}, ROSTER) == "A-1"  # 같으면 agent_id 순
    assert assign("TS_LV", {"A-1": 1}, ROSTER) == "A-2"  # A-1 은 max_open 1 이 찼다
    assert assign("TS_LV", {"A-1": 0, "A-2": 3}, ROSTER) == "A-1"
    assert assign("TS_MV", {"B-1": 99}, ROSTER) == "B-1"  # max_open 0 = 제한 없음
    assert assign("CERT", {}, ROSTER) is None  # 부서에 담당자 없음
    assert assign(None, {}, ROSTER) is None  # 부서 없는 안전 건
    full = [Agent("A-1", "one", "TS_LV", max_open=1)]
    assert assign("TS_LV", {"A-1": 1}, full) is None  # 모두 찼으면 부서 큐


def test_suggest_and_reassign_stay_in_dept() -> None:
    assert [a.agent_id for a in suggest("TS_LV", "A-1", {"A-2": 2}, ROSTER)] == ["A-2"]
    assert reassign("TS_LV", "A-2", ROSTER).name == "two"
    for to, message in [("B-1", "이관"), ("A-3", "비활성"), ("X", "없는")]:
        with pytest.raises(ValueError, match=message):
            reassign("TS_LV", to, ROSTER)


# --- 서비스 · API (메모리, data/ref/agents.csv 명단) ---------------------------------------------

INQUIRY = {
    "channel": "email",
    "customer_tier": "GOLD",
    "language": "en",
    "subject": "Dimensions of TRF-OIL-1000",
    "body": "What are the dimensions and weight of TRF-OIL-1000?",
    "category": "TECH_SPEC",
    "provided_fields": {"application": "substation"},
}


@pytest.fixture
def client():
    with TestClient(
        create_app(
            llm=LLMRouter(Settings(_env_file=None)),
            agents=ANALYSIS,
            storage="memory",
            retrievers=(None, None),
        )
    ) as c:
        yield c


def test_new_tickets_are_spread_over_frontline_agents(client) -> None:
    """담당자는 앞단 글로벌 C/S 센터 상담원이다. 문의 부서(TS_TRF)와 따로다."""
    first = client.post("/api/tickets", json=INQUIRY).json()
    second = client.post("/api/tickets", json=INQUIRY).json()

    assert first["assigned_dept"] == "TS_TRF"
    assert (first["assignee"], second["assignee"]) == ("AG-GCS_L1-01", "AG-GCS_L1-02")
    history = client.get(f"/api/tickets/{first['ticket_id']}/assignments").json()
    assert [(h["from_assignee"], h["to_assignee"], h["reason"]) for h in history] == [
        (None, "AG-GCS_L1-01", "자동 배정")
    ]
    agents = {a["agent_id"]: a for a in client.get("/api/agents?dept=GCS_L1").json()}
    assert agents["AG-GCS_L1-01"]["name"] == "Doyeon Kim"  # 관리자 화면 로그인 계정 (팀장)
    assert {k: a["open_count"] for k, a in agents.items()} == {
        "AG-GCS_L1-01": 1,
        "AG-GCS_L1-02": 1,
        "AG-GCS_L1-03": 0,
        "AG-GCS_L1-04": 0,
    }


def test_reassign_between_frontline_agents_and_reject_specialists(client) -> None:
    tid = client.post("/api/tickets", json=INQUIRY).json()["ticket_id"]

    moved = client.post(
        f"/api/tickets/{tid}/assign",
        json={"assignee": "AG-GCS_L1-02", "reason": "SLA 75% 경고 — 부재", "by": "lead"},
    )
    assert moved.status_code == 200 and moved.json()["assignee"] == "AG-GCS_L1-02"
    rows = client.get("/api/tickets?assignee=AG-GCS_L1-02").json()
    assert [(r["ticket_id"], r["assignee"]) for r in rows] == [(tid, "AG-GCS_L1-02")]
    assert client.get("/api/tickets?assignee=AG-GCS_L1-01").json() == []
    history = client.get(f"/api/tickets/{tid}/assignments").json()
    assert history[-1] == {
        **history[-1],
        "from_assignee": "AG-GCS_L1-01",
        "to_assignee": "AG-GCS_L1-02",
        "reason": "SLA 75% 경고 — 부재",
        "assigned_by": "lead",
    }

    # 같은 사람에게 다시 넘기면 이력을 남기지 않는다
    client.post(f"/api/tickets/{tid}/assign", json={"assignee": "AG-GCS_L1-02"})
    assert len(client.get(f"/api/tickets/{tid}/assignments").json()) == 2

    # 전문부서(문의 부서 TS_TRF 포함) 담당자는 담당자가 될 수 없다 — 이관으로 보낸다
    for specialist in ("AG-TS_TRF-01", "AG-TS_LV-01"):
        other = client.post(f"/api/tickets/{tid}/assign", json={"assignee": specialist})
        assert other.status_code == 409 and "이관" in other.json()["detail"]
    assert client.post(f"/api/tickets/{tid}/assign", json={"assignee": "X"}).status_code == 409
    assert client.post("/api/tickets/NOPE/assign", json={"assignee": "X"}).status_code == 404
    assert client.get("/api/tickets/NOPE/assignments").status_code == 404


def test_escalation_keeps_the_frontline_owner(client) -> None:
    """이관하면 부서는 받는 부서로 바뀌지만, 고객 소통은 앞단 담당자가 계속 맡는다."""
    tid = client.post("/api/tickets", json=INQUIRY).json()["ticket_id"]

    done = client.post(
        f"/api/tickets/{tid}/action", json={"action": "escalate", "escalate_to": "FIELD_SVC"}
    ).json()

    assert (done["assigned_dept"], done["assignee"]) == ("FIELD_SVC", "AG-GCS_L1-01")
    assert len(client.get(f"/api/tickets/{tid}/assignments").json()) == 1
    back = client.post(f"/api/tickets/{tid}/assign", json={"assignee": "AG-GCS_L1-03"})
    assert back.status_code == 200  # 이관 뒤에도 앞단끼리 넘길 수 있다


def test_closed_ticket_cannot_be_reassigned(client) -> None:
    tid = client.post("/api/tickets", json=INQUIRY).json()["ticket_id"]
    client.post(f"/api/tickets/{tid}/action", json={"action": "reject"})

    res = client.post(f"/api/tickets/{tid}/assign", json={"assignee": "AG-GCS_L1-02"})

    assert res.status_code == 409
    assert client.get("/api/agents?dept=GCS_L1").json()[0]["open_count"] == 0  # 닫힌 건은 안 센다
