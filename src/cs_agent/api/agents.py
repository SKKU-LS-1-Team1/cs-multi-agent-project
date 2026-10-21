# 담당자 명단 API (CSA-53 · 담당 김동규)
#
# main.py 에서 "/api" 아래 등록. 명단은 data/ref/agents.csv (services/assignment.py).
# - GET /api/agents?dept=  → list[dict]  담당자 + 지금 열린 건수. dept 가 있으면 그 부서 활성
#   담당자만 (관리자 화면 재배정 선택, CSA-54)
from fastapi import APIRouter

from cs_agent.api.deps import Tickets

router = APIRouter(prefix="/agents", tags=["agents"])


@router.get("")
def agents(tickets: Tickets, dept: str | None = None) -> list[dict]:
    return tickets.agents(dept)
