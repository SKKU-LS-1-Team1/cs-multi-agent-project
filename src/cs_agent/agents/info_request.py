# 추가정보 요청 에이전트 — ⑦ (CSA-27 · 담당 김동규 · Sprint 1)
#
# 그래프의 info_request 노드가 부른다. 두 경우에 불린다.
# - 규칙 처리(⑤) 결과 차단성 필수정보가 빠졌을 때 (route = info_request)
# - 상담원이 관리자 화면에서 "추가정보 요청문 작성" 버튼을 눌렀을 때 (ReviewAction.INFO_REQUEST,
#   상담원이 체크한 항목이 review.info_items 로 들어온다)
#
# 할 일
# 1. 빠진 항목(missing)만, 한 번에 모두 묻는 요청문을 고객 언어(language)로 쓴다. 여러 번 주고받지
#      않게.
# 2. 항목 이름(serial_no, incoterms …)을 고객이 알아듣는 말로 바꾸는 표를 만든다
#    (예: serial_no → "명판 사진의 시리얼 번호"). 항목 목록은 data/ref/required_info.csv 에 있다.
# 3. 문장은 Gemini로 쓴다: llm.write("info_request", prompt). 프롬프트에 문의 요약과 항목 목록을
#      넣는다.
# 4. 고객에게 직접 보내지 않는다 (P-01). 상담원 화면에 초안으로 올라가고, 승인 시 발송 → 상태
#    WAITING_CUSTOMER(SLA 시계 정지). 이 흐름은 graph/builder.py 가 처리한다.
#
# 완료 기준
# - valid 중 missing_info 가 있는 건: 요청문에 빠진 항목이 전부 들어감
# - 15개 언어 중 tickets 비중 상위 언어로 문장 확인 (en 56% 외)
#
# 참고: 기획서 v10 4.2, 관리자_대시보드_AI기능_구조검토.md 3장
#
# 만들 것 (이름·모양은 다른 파일이 이대로 부른다)
#
#   def write_info_request(missing: list[str], language: str, summary: str, llm: LLMRouter) -> str:
#       """빠진 항목 → 고객 언어 요청문 초안."""
