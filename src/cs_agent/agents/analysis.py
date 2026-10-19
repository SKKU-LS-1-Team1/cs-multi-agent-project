# 문의 분석 에이전트 — ② 분류 · ③ 추출 (CSA-26 · 담당 김도연 · Sprint 1)
#
# 그래프의 classify / extract 노드가 부른다. 챗봇(CSA-32)과 문의서 자동 채움(CSA-34)도 그대로 쓴다.
#
# 할 일
# 1. classify(): 문의 유형 10개 중 하나와 확신도를 돌려준다.
#    - 문의서에서 고객이 유형을 골랐으면(inquiry.category) 그 값을 confidence=1.0으로 쓴다.
#    - 기본은 train 분할(2,800건)로 학습한 분류기(TF-IDF + 로지스틱 회귀, valid 99.0% 확인됨,
#      analysis/kpi/KPI_설정안.md). 모델 파일은 data/models/ 에 두고 처음 한 번만 읽는다.
#    - LLM 판단을 쓸 때는 llm.judge("classify", prompt, [c.value for c in Category]) (기획서 9.2:
#        Jev).
#    - secondary_category(복합 의도, 350건)도 채운다. 확률 2위가 기준 이상이면 넣는다.
# 2. extract(): 제품·에러코드·펌웨어·시리얼·긴급도·고객이 준 항목을 뽑는다.
#    - 형식이 정해진 값은 정규식으로 먼저 찾는다: 에러코드(E.OC, E-12, F12 …), 시리얼(S/N …),
#      펌웨어(fw 1.2.3). 주의: "FOB" 같은 일반 단어가 에러코드로 잡히지 않게 한다.
#    - 제품은 data/ref/product_master.csv 의 코드·이름·별칭(S100, iS7, XGI …)으로 찾고,
#      못 찾으면 product_code=None ("미확인"). 제품군(product_family)도 같이 채운다.
#    - 긴급도(Urgency): SAFETY(연기·화재·감전) / SITE_DOWN / PROD_IMPACT / COMMISSION / DEADLINE /
#        NONE.
#      SAFETY는 사람 큐로 바로 가므로(C-08) 놓치면 안 된다. 놓침 0건이 목표.
#    - provided_info: required_info.csv 의 항목 이름(product_model, serial_no, quantity, incoterms
#        …)
#      중 문의에 들어 있는 것. inquiry.provided_fields 의 키도 합친다.
#      수량·인코텀즈·납기일처럼 형식이 제각각인 값은 Gemini 구조화 출력으로 뽑는다.
#    - 영어 키워드는 단어 경계로 찾는다 ("rma"가 "confirmation"에 걸리지 않게).
#
# 완료 기준
# - valid 603건: 유형 정확도 ≥ 95%, 제품 코드 일치율, SAFETY 재현율 100%
# - 결과를 Langfuse에 남긴다 (llm.router 를 거치면 자동)
#
# 참고: 기획서 v10 9장·9.2, analysis/agent-architecture/에이전트_구조_제안.md 2장 ②③
#
# 만들 것 (이름·모양은 다른 파일이 이대로 부른다)
#
#   def classify(inquiry: InquiryIn, llm: LLMRouter) -> Classification:
#       """문의 → 유형·보조 유형·확신도. 위 '할 일 1' 참고."""
#
#   def extract(inquiry: InquiryIn, tables: RefTables | None = None) -> Extraction:
#       """문의 → 제품·에러코드·펌웨어·시리얼·긴급도·제공 항목. 위 '할 일 2' 참고."""
