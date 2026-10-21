# 원문 한국어 번역 (CSA-57 · 담당 김도연 · Sprint 2) — 명세서 C-02
#
# 처리·답변은 원문 기준 그대로 둔다 (분류·추출·검색·답변 작성은 원문을 쓰고, 답변은 고객 언어).
# 여기서는 상담원이 읽을 한국어 번역만 따로 만든다. 관리자 화면 원문/번역 전환은 CSA-58.
#
# 할 일
# 1. 언제: 문의 분석 단계(그래프 classify·extract 와 같은 때). 분석 결과를 기다리지 않게
#    따로 부르고, 번역이 실패해도 처리 흐름은 멈추지 않는다 (번역 없음으로 표시).
# 2. 언어: Extraction.language(없으면 InquiryIn.language)가 "ko" 면 번역하지 않는다 (None).
#    15개 언어 중 상위(en 56% 외)로 품질 확인.
# 3. 그대로 둘 것: 모델명·제품 코드·에러코드·시리얼·숫자·단위·규격명(IEC 60947 등)은 번역하지 않고
#    원문 그대로. 프롬프트에 "번역만, 요약·의역·추가 금지"를 넣는다.
# 4. 모델: llm.write("translate_ko", prompt). 같은 문의는 캐시(CSA-45)로 다시 부르지 않는다.
#    고객 회신(services/tickets.py merge_reply)으로 본문이 길어지면 새로 붙은 부분만 번역해
#    이어 붙인다.
# 5. 저장·표시: tickets.body_ko 열(db/models.py + 마이그레이션), TicketState.body_ko,
#    TicketOut.body_ko. 원문(body)은 바꾸지 않는다.
#
# 완료 기준
# - valid 비한국어 문의: 번역에 원문의 제품 코드·에러코드·숫자가 그대로 다 들어감
# - 번역 실패해도 접수·분석·답변 결과는 같음 (번역 None)
#
# 참고: 명세서 C-02, agents/verification.py (답변 언어 = 고객 언어 점검),
#   agents/analysis.py
#
# 만들 것 (이름·모양은 다른 파일이 이대로 부른다)
#
#   def translate_to_korean(text: str, language: str | None, llm: LLMRouter) -> str | None:
#       """상담원용 한국어 번역. 이미 한국어거나 text 가 비면 None. 실패해도 예외 대신 None."""
#
#   def protected_terms(text: str) -> list[str]:
#       """번역에서 그대로 둘 토큰 (제품 코드·에러코드·숫자+단위·규격명).
#       완료 기준 점검에도 쓴다."""
# TODO(CSA-57): 위 함수 + 그래프 연결(GraphDeps.translate) + body_ko 저장
