# mock 데이터 생성 (CSA-23 · 담당 김동규 · Sprint 1)
# 실행 예: uv run python -m cs_agent.pipeline.mock_data > data/mock/inquiries.json
#
# 화면·API 개발과 시연용 샘플 문의. 실제 시험 데이터(test 597건)는 쓰지 않는다.
#
# 할 일
# 1. 유형 10개 × 제품 몇 개로 InquiryIn 모양의 문의를 만든다 (채널·등급·언어 섞어서).
# 2. 시연 시나리오는 고정값으로 넣는다:
#    - 단순 사양 문의 (TRF-OIL-1000 Vector group) → 추천 답변 → 승인
#    - 안전 건 (연기 발생) → 사람 큐
#    - 필수정보 누락 (S100 트립, 시리얼 없음) → 추가정보 요청
#    - 챗봇 경유 (S100 E.OC → 조치 후 재발 → 문의하기 자동 채움)
# 3. POST /api/tickets 로 한 번에 넣는 스크립트 옵션.
