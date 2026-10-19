# KPI 계산 (CSA-49 기준선 측정 · 담당 김동규 · Sprint 1)
#
# 정의·목표치는 analysis/kpi/KPI_설정안.md 를 따른다.
#   K1 처리 지연 p95 (목표 ≤ 60초, Langfuse 기록)
#   K2 무수정 승인 가능률 (정보 안내형)
#   K3 근거 일치율 (reference_doc_id + reference_section)
#   K4 부서·우선순위 일치율 (부서는 100% 게이트)
#   K5 필수정보 누락 탐지율 (missing_info 재현율)
#
# 할 일
# 1. accuracy(pred, gold), p95(values), recall(pred_sets, gold_sets) 같은 계산 함수
# 2. 기준선: valid 603건으로 현재 값을 재고 목표치를 확정해 KPI_설정안.md 에 기록
# 3. Jev vs Gemini 비교 (정확도·응답 시간·비용) 표 (기획서 9.2)
