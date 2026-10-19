# 문의 전환 판단 (CSA-35 기준값 확정 · 담당 박종석 · Sprint 2)
#
# 챗봇이 "문의하기"로 넘길지 정한다. 코드로 판단한다.
#
# 전환 조건 (기획서 5.5)
# - 고객이 해결 안 됐다고 답함 / 상담원 연결 요청
# - 원격 조치 후 같은 증상 재발 (기술 진단형)
# - 결정이 필요한 문의: 견적서 발행, 납기 확약, 보증·반품 승인
# - 근거 문서를 못 찾음: 검색 1등 점수 < MIN_RETRIEVAL_SCORE
#
# 할 일
# 1. should_handoff() 를 위 조건 순서대로 구현하고, 넘기는 이유를 고객에게 보일 한 줄로 reason 에
#      넣는다.
# 2. MIN_RETRIEVAL_SCORE, MAX_REMOTE_RETRIES 를 정한다: valid 문의로 검색 점수 분포를 보고
#    (CSA-28·CSA-50 결과), "답이 있는 질문"과 "없는 질문"을 가르는 값을 고른다. 근거를 주석에
#      남긴다.
#
# 완료 기준: 정한 기준값과 근거(분포 그림 또는 수치)를 PR에 첨부
#
# 만들 것 (이름·모양은 다른 파일이 이대로 부른다)
#
#   MIN_RETRIEVAL_SCORE: float | None = None  # 할 일 2
#
#   MAX_REMOTE_RETRIES: int | None = None  # 할 일 2
#
#   @dataclass
#   class HandoffDecision:
#       handoff: bool
#       reason: str = ""
#
#   def should_handoff(
#       category: Category | None,
#       best_score: float,
#       customer_unresolved: bool = False,
#       remote_attempts: int = 0,
#   ) -> HandoffDecision:
