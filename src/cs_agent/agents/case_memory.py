# 사례 기반 RAG — 해결 확정 문의를 사례 DB(`cases`)에 저장 (기획서 7.1 · 담당 김동규 ·
#   CSA-15·CSA-25)
#
# services/tickets.py 의 resolve() 가 부른다.
#
# 할 일
# 1. 저장 시점: 승인·발송이 아니라 문의가 '해결(RESOLVED)'로 바뀔 때.
#    - 그대로 승인 / 수정 후 승인 → 저장 (수정본이면 수정본 + 수정 사유)
#    - 전문부서 이관 → 이관 부서가 해결 확정하면 저장
#    - AI 재작성 중간본 · 추가정보 요청 · 반려 → 저장하지 않음
#    SAVE_ON 에 저장 대상 상담원 행동을 정의한다.
# 2. build_case(): 그래프 상태 → 사례 문서 (요약, 제품·유형·에러코드, 원인, 조치, 최종 답변, 근거,
#      수정 사유).
# 3. 개인정보 가리기: 회사명·연락처·시리얼 번호 (mask_pii).
# 4. 저장: ChromaDB `cases` 컬렉션 upsert + PostgreSQL resolution_cases 테이블 (CSA-24).
# 5. 재문의로 다시 열린 문의의 사례는 검색 대상에서 잠시 뺀다.
# 6. 사실 오류(FACT_ERROR)로 고친 건은 원천(기준표·문서)도 고치도록 알림을 남긴다.
#
# 완료 기준
# - 시연: test 문의를 순서대로 처리하며 해결 건을 쌓고, 앞 절반 vs 뒤 절반 무수정 승인율 비교
#     (CSA-15)
#
# 참고: 기획서 v10 7장·7.1
#
# 만들 것 (이름·모양은 다른 파일이 이대로 부른다)
#
#   SAVE_ON: set[ReviewAction] = set()
#
#   def mask_pii(text: str) -> str:
#
#   def build_case(state: dict) -> dict:
