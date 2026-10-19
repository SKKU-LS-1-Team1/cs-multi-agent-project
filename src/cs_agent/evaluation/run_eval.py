# 시험 문의 평가 스크립트 (CSA-50 · 담당 박종석) → 최종 결과 정리 (CSA-51)
# 실행 예: uv run --extra data python -m cs_agent.evaluation.run_eval --split valid
#
# test 597건은 마지막에 한 번만 돌린다 (N-05). 개발 중에는 --split valid (603건).
#
# 할 일
# 1. data/processed/tickets_{split}.parquet 를 읽어 문의마다 TicketService.submit() 실행, 지연
#      시간 기록.
# 2. 정답과 비교: 유형(category_code), 부서(assigned_dept), 우선순위(priority), 누락
#      항목(missing_info),
#    근거(reference_doc_id, reference_section), 추가정보 요청 여부(info_request_sent).
# 3. evaluation/metrics.py 로 K1~K5 계산, JSON + 표로 저장
#      (data/processed/eval_{split}_{날짜}.json).
# 4. 유형별·언어별로 쪼개 본다. 틀린 건 목록을 따로 남겨 담당자에게 넘긴다.
# 5. 시연(CSA-15): test 를 순서대로 처리하며 해결 건을 사례 DB 에 쌓고, 앞 절반 vs 뒤 절반 비교.
