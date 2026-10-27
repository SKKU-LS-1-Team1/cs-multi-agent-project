from datetime import UTC, datetime, timedelta

from fastapi import FastAPI
from fastapi.testclient import TestClient
from test_db import db as db
from test_db import needs_db

from cs_agent.api.customers import router
from cs_agent.services.customers import summarize_customers

NOW = datetime(2026, 10, 27, tzinfo=UTC)


def row(**patch):
    return {
        "ticket_id": "T-1",
        "customer_id": "C-1",
        "customer_tier": "GOLD",
        "country": "FR",
        "language": "fr",
        "received_at": NOW - timedelta(hours=48),
        "subject": "Inquiry",
        "product_family": "DRIVE",
        "priority": "P2",
        "category": "DEFECT",
        "status": "ON_HOLD",
        "urgency_flag": "NONE",
        "resolved_at": None,
        "sla_resolution_target_h": 24,
        "customer_wait_hours": 0,
        "waiting_since": None,
        **patch,
    }


def test_empty_database_and_unidentified_inquiry_do_not_create_demo_customers():
    assert summarize_customers([], NOW) == []
    assert summarize_customers([row(customer_id=None)], NOW) == []


def test_current_customer_groups_and_history_use_actual_ticket_ids():
    result = summarize_customers(
        [
            row(),
            row(ticket_id="T-2", received_at=NOW, customer_tier="PLATINUM", product_family=None),
        ],
        NOW,
    )
    assert len(result) == 1
    c = result[0]
    assert (c["id"], c["name"], c["tier"], c["n"], c["breach"]) == ("C-1", "C-1", "PLATINUM", 2, 1)
    assert c["since"] == ""
    assert c["fam"] == [("DRIVE", 1)]
    assert c["urgent"][0][0] == "T-1"
    assert c["t"][0][0] == "T-2"
    assert {t["id"] for t in c["notice_tickets"]} == {"T-1", "T-2"}
    assert all(t["language"] == "fr" for t in c["notice_tickets"])


def test_customer_wait_freezes_sla_and_resume_uses_accumulated_wait():
    waiting = row(status="WAITING_CUSTOMER", waiting_since=NOW - timedelta(hours=40))
    assert summarize_customers([waiting], NOW)[0]["urgent"] == []
    resumed = row(customer_wait_hours=40)
    assert summarize_customers([resumed], NOW)[0]["urgent"] == []
    imminent = row(customer_wait_hours=30)
    assert summarize_customers([imminent], NOW)[0]["urgent"][0][4] == 18


def test_safety_is_included_without_sla_and_removed_when_resolved():
    safe = row(customer_tier="STANDARD", urgency_flag="SAFETY", sla_resolution_target_h=None)
    c = summarize_customers([safe], NOW)[0]
    assert c["safety"] == [["T-1", "Inquiry"]]
    assert c["urgent"] == []
    c = summarize_customers([{**safe, "status": "RESOLVED", "resolved_at": NOW}], NOW)[0]
    assert c["safety"] == c["notice_tickets"] == []


def test_history_window_and_closed_sla_do_not_keep_aging():
    old = row(
        received_at=NOW - timedelta(days=500),
        status="RESOLVED",
        resolved_at=NOW - timedelta(days=499, hours=12),
    )
    c = summarize_customers([old], NOW)[0]
    assert c["n"] == c["breach"] == 0
    assert c["fam"] == c["urgent"] == []
    assert c["t"][0][-1] == "MET"


def test_customer_api_without_database_returns_503_not_sample_data():
    app = FastAPI()
    app.state.sessionmaker = None
    app.include_router(router, prefix="/api")
    with TestClient(app) as client:
        assert client.get("/api/customers").status_code == 503


@needs_db
def test_postgres_customer_api_reads_current_rows_without_writing_history(db):
    from uuid import uuid4

    from sqlalchemy.orm import Session

    from cs_agent.api.deps import _db
    from cs_agent.db.models import Ticket

    engine, _ = db
    cid = f"customer-test-{uuid4().hex[:12]}"
    app = FastAPI()
    app.include_router(router, prefix="/api")
    try:
        with engine.connect() as connection:
            transaction = connection.begin()
            session = Session(bind=connection)
            try:
                now = datetime.now(UTC)
                session.add(
                    Ticket(
                        ticket_id=f"T-{uuid4().hex[:20]}",
                        customer_id=cid,
                        customer_tier="STANDARD",
                        channel="email",
                        country="FR",
                        language="fr",
                        subject="Safety check",
                        body="Synthetic test",
                        status="HUMAN_QUEUE",
                        urgency_flag="SAFETY",
                        received_at=now,
                    )
                )
                session.flush()
                app.dependency_overrides[_db] = lambda: session
                with TestClient(app) as client:
                    response = client.get("/api/customers")
                assert response.status_code == 200
                customer = next(c for c in response.json() if c["id"] == cid)
                assert customer["n"] == 1
                assert len(customer["safety"]) == 1
                assert customer["notice_tickets"][0]["language"] == "fr"
                assert customer["notice_tickets"][0]["id"] == customer["t"][0][0]
                assert customer["fam"] == []
            finally:
                session.close()
                transaction.rollback()
    finally:
        engine.dispose()
