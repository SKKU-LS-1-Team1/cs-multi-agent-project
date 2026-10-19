# 문의서 작성 에이전트 (CSA-34 · 담당 조수빈 · Sprint 2)
#
# 챗봇이 문의하기로 넘길 때, 대화에서 얻은 값으로 문의서 칸을 미리 채운다 (기획서 5.5 표).
# 제출은 고객이 확인한 뒤 직접 누른다. 고객이 고친 값이 우선하고, 고친 칸은 추출 정확도 측정에 쓴다.
#
# 할 일
# 1. 유형별 필수 항목 목록: rules/engine.py 의 required_info(family, category) 로 칸을 만든다.
# 2. 대화에서 찾은 값(제품, 에러코드, 시리얼, 펌웨어, 수량 …)을 fields 에 넣고,
#    빈 필수 항목은 missing_required 에 넣는다 (화면에서 빨간 칸, 채우기 전 제출 불가).
# 3. subject·body: Gemini로 대화를 요약한다. 이미 안내받은 조치와 그 결과를 꼭 넣는다
#    ("가속 시간 조정 후에도 재발") — 상담원이 같은 조치를 다시 안내하지 않게.
# 4. 국가·언어·회사·연락처는 로그인 고객 정보에서 (화면 쪽에서 합친다).
#
# 완료 기준: 기획서 5.5 예시(불량 문의)대로 채워진 문의서가 나온다
#
# 만들 것 (이름·모양은 다른 파일이 이대로 부른다)
#
#   class InquiryDraftForm(BaseModel):
#       """문의하기 화면에 넘기는 문의서 초안. 화면(frontend/src/api/client.ts)과 같은 모양."""
#
#       category: str | None = None
#       product_code: str | None = None
#       fields: dict[str, str] = Field(default_factory=dict)
#       missing_required: list[str] = Field(default_factory=list)
#       subject: str = ""
#       body: str = ""
#
#   def fill_form(
#       classification: Classification, extraction: Extraction, transcript: list[str]
#   ) -> InquiryDraftForm:
