# 챗봇 대화 에이전트 (CSA-32 · 담당 조수빈 · Sprint 2)
#
# api/chat.py 의 POST /api/chat 이 부른다. 대화 기록은 cache/store.py 의 ChatSessionStore(Redis)에
#   있다.
#
# 할 일
# 1. respond(): 대화 기록 + 새 메시지로 InquiryIn 을 만들고 (viewing_product 를 product_code 로),
#    문의 분석(agents/analysis.py)으로 유형·제품·에러코드를 뽑는다. 새로 만들지 말고 재사용한다.
# 2. 지식 검색(agents/retrieval.py)으로 근거를 찾는다. 제품을 알면 where={"product_code": …}.
# 3. 화면 이동(chatbot/navigation.py decide)을 정한다.
# 4. 문의 전환(chatbot/handoff.py should_handoff)이면: 이유 한 줄 + "문의하기로 이동" 답변,
#    handoff=True, form=fill_form(...) (chatbot/form_filler.py).
# 5. 아니면 Gemini로 고객 언어 답변: llm.write("chat_answer", …). 공개 문서 근거 안에서만 답한다.
#    견적 금액 확정·보증 승인·원인 단정은 하지 않는다.
# 6. 유형별 필수 항목 중 아직 안 나온 것 1~2개를 ask_fields 에 넣어 미리 묻는다 (예: 불량 → 시리얼).
#    필수 항목 목록은 rules/engine.py required_info().
# 7. 대화 의도·재문의·해결 여부 판단은 Jev(llm.judge)로 (기획서 9.2).
#
# 완료 기준: 기획서 5.4·5.5 시나리오(S100 E.OC → 고장 탭 → 재발 → 문의하기 자동 채움)가 끝까지 동작
#
# 참고: 기획서 v10 5장
#
# 만들 것 (이름·모양은 다른 파일이 이대로 부른다)
#
#   class ChatIn(BaseModel):
#       session_id: str
#       message: str
#       language: str = "en"
#       viewing_product: str | None = None  # 대시보드에서 보고 있는 제품 (양방향 연동)
#       unresolved: bool = False  # 고객이 "해결 안 됐어요"를 누름
#
#   class ChatOut(BaseModel):
#       answer: str
#       navigation: Navigation
#       evidence: list[Evidence] = Field(default_factory=list)
#       ask_fields: list[str] = Field(default_factory=list)
#       handoff: bool = False
#       handoff_reason: str = ""
#       form: InquiryDraftForm | None = None
#
#   def respond(chat: ChatIn, history: list[str], docs: Retriever, llm: LLMRouter) -> ChatOut:
