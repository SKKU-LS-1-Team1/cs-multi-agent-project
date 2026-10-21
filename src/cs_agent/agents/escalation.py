# 이관 요청서 작성 에이전트 (CSA-55 · 담당 김도연 · Sprint 2) — 명세서 S-07 확장
#
# 상담원이 관리자 화면에서 이관(ReviewAction.ESCALATE)을 고르기 전에, 받는 부서에 보낼 요청서
# 초안을 만든다. 상담원이 검토·수정해서 전달한다 (화면은 CSA-56).
#
# 이관 대상: CERT(인증·규격) · FIELD_SVC(현장 서비스) · QA_CLAIM(품질보증/클레임).
#   routing_rules.csv 의 escalation_dept 에는 SALES_OPS·RND_FW·TS_* 도 있다 → 이 셋만 요청서를 쓸지,
#   전부 쓸지 정해서 ESCALATION_TARGETS 에 적는다.
#
# 할 일
# 1. 부서 제안: RuleResult.escalate_to (routing_rules escalation_dept) 를 기본값으로, 사유는
#    escalation_condition 문장(예: "P1/P2 이거나 현장 확인이 필요한 경우")에서 가져온다.
#    상담원이 다른 부서를 고르면 그 부서 기준으로 다시 쓴다.
# 2. 요청서 칸 (부서마다 받는 쪽이 꼭 봐야 하는 것):
#    - 공통: 문의 요약, 제품(product_code·family), 고객 등급·국가, 우선순위·SLA 마감, 이관 사유
#    - FIELD_SVC: 설치 위치·현장 조건, 에러코드, 지금까지 원격 점검 결과, 방문 희망 일정
#    - QA_CLAIM: 불량 증상, 시리얼·로트, 사진·성적서 유무, 반품 여부(return_defect)
#    - CERT: 요청 규격·인증서 종류, 대상 모델, 시험성적서 필요 여부
#    값(제품·우선순위·SLA·에러코드)은 상태(TicketState)에서 그대로 쓰고 LLM 이 만들지 않는다.
# 3. 진단 요약·근거: 답변 초안(draft)·근거(evidence, docs 상위 3개)·자동 점검 결과에서 뽑는다.
#    근거는 "doc_id#section" 으로 붙인다 (관리자 화면 근거 번호와 같게).
# 4. 문장: 한국어(사내 요청서). llm.write("escalation_request", prompt). 빈 칸은 "확인 필요"로 둔다.
# 5. 연결: GraphDeps.write_escalation_request (graph/builder.py). 이관 버튼 전 "요청서 만들기"로
#    부르거나 escalate 노드에서 만든다 → 결과는 drafts 테이블 kind="escalation" 로 남긴다
#    (db/models.py DraftRow.kind 에 값 추가). TicketOut 에 escalation_request 추가.
#
# 완료 기준
# - valid 중 escalate_to 가 있는 문의: 부서·사유·진단 요약·근거가 모두 채워진 요청서
# - 상태에 있는 값(제품·우선순위·SLA)이 요청서와 다르면 0건
#
# 참고: 명세서 S-07, data/ref/routing_rules.csv · departments.csv,
#   agents/drafting.py (프롬프트 모양)
#
# 만들 것 (이름·모양은 다른 파일이 이대로 부른다)
#
#   ESCALATION_TARGETS: frozenset[str] = frozenset({"CERT", "FIELD_SVC", "QA_CLAIM"})
#
#   class EscalationRequest(BaseModel):          # schemas.py 로 옮긴다
#       to_dept: str
#       reason: str
#       summary: str                             # 진단 요약
#       fields: dict[str, str]                   # 부서별 칸 (할 일 2)
#       cited: list[str]                         # ["doc_id#section"]
#       text: str                                # 상담원이 고칠 요청서 본문
#       model: str = ""
#
#   def write_escalation_request(state: TicketState, llm: LLMRouter,
#                                to_dept: str | None = None) -> EscalationRequest:
#       """이관 요청서 초안. to_dept 가 없으면 rules.escalate_to."""
# TODO(CSA-55): 위 함수 + GraphDeps 연결 + drafts kind="escalation"
