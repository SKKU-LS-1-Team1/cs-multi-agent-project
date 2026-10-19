# 답변 작성 에이전트 — ⑨ (CSA-29 정보 안내형 · CSA-30 유형별 확장 · 담당 김도연)
#
# 그래프의 draft 노드가 부른다. 노드 1개 + 유형별 틀 10개로 만든다.
#
# 묶음별 모드 (기획서 3장, domain.BUNDLE_OF)
# - 정보 안내형 (TECH_SPEC, MANUAL, COMPLIANCE, QUOTE, ORDER_LEAD): 그대로 보낼 수 있는 완성 답변
# - 기술 진단형 (DEFECT, INSTALL, FW_UPDATE): 원인 후보·점검 순서·추가로 받을 자료. 원인 단정 금지.
#   원격 해결이 안 되면 현장 점검·수리 접수 제안
# - 정책 판단형 (WARRANTY, RETURN): 보증기간 내 여부·필요 서류·정책 조항. 승인·반려 문장 금지
#
# 할 일
# 1. TEMPLATES: 유형마다 Template(name, required_slots, guide)를 정의한다.
#    예) QUOTE = 단가·수량·합계·납기·유효기간 슬롯이 모두 있어야 함 (하나라도 비면 자동 점검 실패).
#    Sprint 1(CSA-29)은 정보 안내형 5개, Sprint 2(CSA-30)는 나머지 5개.
# 2. build_slots(): 슬롯 값을 코드로 채운다 (제품명, 근거 문서·절, 사양값, 정가, 납기, 보증기간 …).
#    값은 기준표(CSA-19)에서 조회한다. 숫자를 LLM이 만들지 않는다.
# 3. write_draft(): Gemini로 문장을 쓴다 — llm.write("draft", prompt).
#    프롬프트 = 모드 지침 + 틀 가이드 + 고객 언어 + 슬롯 값(그대로 쓸 것) + 근거 원문 + 문의 원문.
#    - fix_notes: 자동 점검(⑩) 실패 사유. 있으면 "지난 점검 실패 사유"로 넣어 고치게 한다.
#    - reviewer_feedback: 상담원 "AI 재작성 요청"의 피드백 한 줄. 있으면 "상담원 지적"으로 넣는다.
#    - 복합 의도(secondary_category)면 같은 호출에서 두 번째 틀 섹션을 덧붙인다.
#    - cited 에 근거 "doc_id#section" 목록을 넣는다 (관리자 화면 근거 번호 표시용).
# 4. 해결 사례(cases)는 문장 본보기로만 쓰고, 값은 docs 쪽을 따른다.
#
# 완료 기준
# - valid 정보 안내형: 자동 점검 통과율, K2(무수정 승인 가능률) 기준선 측정
# - 진단형·정책형 답변에 금지 표현 0건
#
# 참고: 기획서 v10 3장·4.1, 에이전트_구조_제안.md 3장
#
# 만들 것 (이름·모양은 다른 파일이 이대로 부른다)
#
#   @dataclass(frozen=True)
#   class Template:
#       name: str
#       required_slots: tuple[str, ...]
#       guide: str
#
#   TEMPLATES: dict[Category, Template] = {}
#
#   def build_slots(extraction: Extraction, evidence: list[Evidence]) -> dict[str, str]:
#       """⑧에서 코드로 채우는 슬롯 값."""
#
#   def write_draft(
#       category: Category,
#       extraction: Extraction,
#       evidence: list[Evidence],
#       inquiry_text: str,
#       llm: LLMRouter,
#       fix_notes: list[str] | None = None,
#       reviewer_feedback: str | None = None,
#   ) -> Draft:
#       """유형별 틀로 추천 답변 작성."""
