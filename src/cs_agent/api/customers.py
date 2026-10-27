"""관리자 고객 목록: 실제 DB 문의에서 요약 조회. DB가 없으면 503."""

from fastapi import APIRouter
from sqlalchemy import select

from cs_agent.api.deps import DB
from cs_agent.db.models import Ticket
from cs_agent.services.customers import summarize_customers

router = APIRouter(prefix="/customers", tags=["customers"])


@router.get("")
def customers(db: DB) -> list[dict]:
    names = (
        "ticket_id",
        "customer_id",
        "customer_tier",
        "country",
        "language",
        "received_at",
        "subject",
        "product_family",
        "priority",
        "category",
        "status",
        "urgency_flag",
        "resolved_at",
        "sla_resolution_target_h",
        "customer_wait_hours",
        "waiting_since",
    )
    rows = db.execute(select(*(getattr(Ticket, name) for name in names))).mappings().all()
    return summarize_customers([dict(row) for row in rows])
