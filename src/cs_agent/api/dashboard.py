# 부서별 대시보드 API (CSA-43 · 담당 김도연)
#
# router = APIRouter(prefix="/dashboard")
# - GET /api/dashboard/departments → 부서별 진행 중 건수, SLA 75% 경고 건수, 위반 건수,
#   그대로 승인·수정·반려 비율 (유형별, 주 단위)
# 쿼리는 박종석 님 db/sql/dept_dashboard.sql (CSA-20)을 쓴다.

from fastapi import APIRouter

# TODO: 위 엔드포인트를 이 라우터에 만든다 (main.py 가 이미 /api 아래 등록해 둠)
router = APIRouter(prefix="/dashboard", tags=["dashboard"])
