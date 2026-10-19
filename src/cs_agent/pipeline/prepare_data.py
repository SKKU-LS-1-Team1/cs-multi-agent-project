# 상담 이력 정제, 학습·시험 분리 (CSA-17 · 담당 박종석 · Sprint 1)
# 실행 예: uv run --extra data python -m cs_agent.pipeline.prepare_data
#
# 입력: data/raw/cs_tickets_resolution_v1.xlsx
#   - tickets 4,000행 × 58열 (data_split: train 2,800 / valid 603 / test 597)
#   - resolution_cases 800행 × 27열
#   (/mnt/project-files/.notes/inputs.md 에 열 설명이 있다)
# 출력: data/processed/ 에 tickets_train / tickets_valid / tickets_test / cases_seed (parquet)
#
# 할 일
# 1. data_split 열 그대로 나눈다.
# 2. 정제: 중복 제거, 언어 코드 정리(language vs body_language), 마스킹 상태 확인.
# 3. resolution_cases 중 valid·test 티켓에 연결된 사례(104건+)는 cases_seed 에서 뺀다 (N-05, 평가
#      공정성).
#    기획서 7.1 기준으로는 해결 사례 568건 + 상담 이력 해결 건 2,557건을 처음 적재.
# 4. 분류기 학습용 train 텍스트(subject + body)와 정답(category_code)을 따로 저장 (김도연 님
#      CSA-26).
# 5. 결과 건수를 출력한다.
