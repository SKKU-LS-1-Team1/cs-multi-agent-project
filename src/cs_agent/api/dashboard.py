"""부서별 대시보드 API (CSA-43 · 담당 김도연). TODO(CSA-20): db/sql/dept_dashboard.sql로 교체."""

from collections import Counter

from fastapi import APIRouter

from cs_agent.api.deps import Tickets

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/departments")
def departments(svc: Tickets) -> list[dict]:
    rows = svc.work_list()
    counts = Counter(r["assigned_dept"] for r in rows)
    at_risk = Counter(r["assigned_dept"] for r in rows if r["at_risk"])
    return [{"dept": d, "open": n, "at_risk": at_risk[d]} for d, n in counts.most_common()]
