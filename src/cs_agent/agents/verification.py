# 자동 점검(검증) 에이전트 — ⑩ (CSA-31 · 담당 김동규 · Sprint 2)
#
# 그래프의 verify 노드가 부른다. 실패하면 실패 사유를 답변 작성(⑨)에 넘겨 재작성하고,
# 최대 2회(settings.max_verify_retries, S-06) 넘으면 보류(ON_HOLD, P-03)로 상담원 화면에 올린다.
# 재시도·보류 분기는 graph/builder.py 가 이미 처리한다. 여기서는 점검 결과 목록만 돌려준다.
#
# 할 일 — 코드 점검 1~5를 먼저 하고, 모두 통과했을 때만 6(LLM)을 부른다 (호출 수·속도 절약)
# 1. slots: 틀의 필수 슬롯이 다 찼는가 (drafting.TEMPLATES[category].required_slots)
# 2. values: 답변 속 수치·문서 ID가 슬롯(조회값)과 같은가 (정규식으로 값 뽑아 비교)
# 3. specs: 고객이 말하지 않았고 근거에도 없는 사양(kV, kA, kW, IEC/UL …)을 넣었는가 (C-05).
#    비교할 때 공백 차이("1000 kVA" vs "1000kVA")는 무시한다.
# 4. language: 답변 언어 = 고객 언어 (C-02). 언어 감지 라이브러리 사용
# 5. banned: 진단형이 원인을 단정했나 / 정책형이 승인·반려를 썼나 (금지 표현 목록)
# 6. grounding: 모든 문장이 근거에서 나왔는가 — llm.judge("verify_grounding", …, ["yes","no"])
#    근거 없는 문장 번호를 받아 reason 에 넣으면 재작성 때 그대로 쓴다.
#
# 각 점검은 CheckResult(name, passed, reason)로 돌려준다. reason 은 사람이 읽는 실패 사유
# ("견적 유효기간 누락", "2번 문장 근거 없음")로 쓴다. 관리자 화면(CSA-42)에 그대로 표시된다.
#
# 완료 기준
# - 일부러 틀린 값·근거 없는 문장을 넣은 답변을 잡아낸다 (사례 10개 이상으로 확인)
# - valid에서 점검 통과율·재작성 횟수 분포 보고
#
# 참고: 에이전트_구조_제안.md 4장
#
# 만들 것 (이름·모양은 다른 파일이 이대로 부른다)
#
#   def verify(
#       draft: Draft,
#       category: Category,
#       required_slots: tuple[str, ...],
#       inquiry_text: str,
#       language: str,
#       evidence: list[Evidence],
#       llm: LLMRouter,
#   ) -> list[CheckResult]:
#       """점검 1~6 결과 목록. 위 '할 일' 참고."""
