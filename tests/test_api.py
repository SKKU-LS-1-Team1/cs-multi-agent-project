from fastapi.testclient import TestClient

from cs_agent.main import create_app


def test_ticket_flow_and_products(deps):
    client = TestClient(create_app(deps))
    assert client.get("/api/health").json()["status"] == "ok"

    tree = client.get("/api/products/tree").json()
    assert len(tree) == 3
    assert sum(len(d["families"]) for d in tree) == 11
    assert sum(len(f["products"]) for d in tree for f in d["families"]) == 23

    t = client.post(
        "/api/tickets",
        json={"body": "Vector group of TRF-OIL-1000?", "provided_fields": {"application": "x"}},
    ).json()
    assert t["status"] == "READY_FOR_REVIEW"
    assert t["draft"]["text"]

    work = client.get("/api/tickets").json()
    assert work[0]["ticket_id"] == t["ticket_id"]

    done = client.post(
        f"/api/tickets/{t['ticket_id']}/action",
        json={"action": "edit_approve", "edited_text": "Dyn11 입니다.", "feedback_reason": "TONE"},
    ).json()
    assert done["status"] == "APPROVED"


def test_chat_navigation_and_handoff(deps):
    client = TestClient(create_app(deps))
    r = client.post("/api/chat", json={"session_id": "s1", "message": "TRF-OIL-1000 vector group"})
    body = r.json()
    assert body["navigation"]["product_code"] == "TRF-OIL-1000"
    assert body["handoff"] is False

    r = client.post("/api/chat", json={"session_id": "s1", "message": "Please quote 20 units"})
    body = r.json()
    assert body["handoff"] is True
    assert body["form"]["category"] == "QUOTE"
    assert "quantity" in body["form"]["missing_required"]
