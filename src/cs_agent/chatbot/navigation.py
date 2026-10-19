# 화면 이동 규칙표 + 화면 이동 에이전트 (CSA-33 · 담당 조수빈 · Sprint 2)
#
# 챗봇 응답에 담겨 고객 화면 대시보드를 움직이는 지시(제품, 탭, 강조 항목)를 정한다.
# AI는 제품·유형·에러코드를 뽑는 데까지만 쓰고(문의 분석 CSA-26), 어느 탭으로 갈지는 규칙표가
#   정한다.
# 같은 질문에는 항상 같은 칸이 열려야 한다.
#
# 할 일
# 1. data/ref/navigation_rules.csv 를 확정한다 (기획서 5.4 표). 열: nav_rule_id, intent, tab,
#      anchor.
#    intent = PRODUCT_ONLY / FAMILY_ONLY / 유형 10개. tab = info | install | faults | firmware |
#      docs | faq | tree.
# 2. decide():
#    - 제품을 모르고 제품군만 알면 → FAMILY_ONLY: 화면은 그대로, candidates 에 그 제품군 제품 코드
#        목록
#      (챗봇이 "제품 선택" 버튼으로 보여준다)
#    - 제품만 알고 유형 확신도가 낮으면 → PRODUCT_ONLY (제품 정보 탭)
#    - 둘 다 알면 → 유형 규칙. anchor 가 error_code 면 추출된 에러코드를 넣는다 (고장 탭에서 그
#        코드 강조)
#    - 아무것도 모르면 → 이동 없음
# 3. 고객이 대시보드에서 직접 다른 제품·탭을 누르면 그 화면이 다음 대화의 맥락이 된다
#    (ChatIn.viewing_product). 이 연동은 chatbot/agent.py 에서 쓴다.
#
# 완료 기준: 기획서 5.4 표의 예 8개("iS7 75kW 알려줘", "S100 가속 중 E.OC" …)가 표대로 이동
#
# 만들 것 (이름·모양은 다른 파일이 이대로 부른다)
#
#   class Navigation(BaseModel):
#       """챗봇 응답에 담기는 이동 지시. 화면(frontend/src/api/client.ts)과 같은 모양."""
#
#       product_code: str | None = None
#       tab: str | None = None
#       anchor: str | None = None
#       rule_id: str | None = None
#       candidates: list[str] = Field(default_factory=list)
#
#   def decide(
#       extraction: Extraction,
#       classification: Classification | None,
#       tables: RefTables | None = None,
#       min_confidence: float = 0.5,
#   ) -> Navigation:
#       """추출·분류 결과 → 이동 지시. 위 '할 일 2' 참고."""
