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
# 기준값 근거 (2026-10-20 측정, #22 이후 문서 글 모양으로 다시 잼)
# 다시 재기: LLM_PROVIDER=live uv run --extra llm --extra data \
#              python -m cs_agent.evaluation.handoff_threshold --split valid
#
# MIN_RETRIEVAL_SCORE = 0.70
# - 점수 = 지식 검색 docs 1등의 cosine 유사도 (agents/retrieval.py PgVectorRetriever 의
#   score = 1 - 거리). gemini-embedding-2 · 1536차원, 문서 글은 적재와 같은
#   embed_docs.doc_rows() 의 text(Chunk.embedding_text: 문서 종류·제품·상위 절 경로 + 본문),
#   제품 필터 없이 전체 문서 813조각에서 잰 값.
# - 답이 있는 질문: valid 603건 → 최저 0.595, 하위 5% 0.759, 중앙값 0.811.
#   0.70 아래는 3건뿐이고 모두 ORDER_LEAD(본문이 아주 짧음) → 어차피 '결정 필요'로 넘어간다.
#   결정 유형을 뺀 407건은 최저 0.732.
# - 답이 없는 질문: 가전·여행·채용·날씨·없는 제품 등 범위 밖 질문 48개(16개 언어,
#   data/eval/handoff_out_of_scope.txt) → 최고 0.649 ("XYZ-9000 위성용 배터리"), 중앙값 0.536.
# - 0.649 와 0.732 사이 빈 구간에서 0.70: 결정 유형 외 valid 100% 답변, 범위 밖 100% 전환.
#   양쪽 여유 0.051 / 0.032. 애매하면 상담원으로 넘기는 쪽.
#   (#22 이전 문서 글로 잰 값은 0.648 / 0.738 — 문맥을 붙여도 구간이 유지됐다)
# - 1등 점수로는 "엉뚱한 문서를 1등으로 찾은 건"(정답이 top-3 밖, 249건, 중앙값 0.800)은 못
#   가른다 — 그건 검색 품질(K3) 문제다.
# - 임베딩 모델·차원·문서 글 모양이 바뀌면 위 명령으로 다시 잰다.
#
# MAX_REMOTE_RETRIES = 2
# - 진단형(DEFECT·INSTALL·FW_UPDATE) tickets 에서 재문의 횟수별 현장 출동·RMA 비율:
#   0회 23% (193/826) → 1회 31% (108/351) → 2회 50% (14/28).
#   원격 조치 후 한 번 재발한 건은 아직 70%가 원격으로 풀리고, 두 번째 재발부터 절반이 현장행이다.
# - 그래서 원격 조치가 2번 실패하면 넘긴다. 고객이 "해결 안 됐어요"를 누르면 횟수와 상관없이
#   1번 조건으로 바로 넘어간다 (기획서 5.5 S100 E.OC 시나리오).
from dataclasses import dataclass

from cs_agent.domain import BUNDLE_OF, Bundle, Category

MIN_RETRIEVAL_SCORE: float | None = 0.70
MAX_REMOTE_RETRIES: int | None = 2

# 챗봇이 확정할 수 없는 결정: 견적서 발행·납기 확약·보증 승인·반품 승인
DECISION_CATEGORIES = frozenset(
    {Category.QUOTE, Category.ORDER_LEAD, Category.WARRANTY, Category.RETURN}
)

# 고객에게 보일 한 줄 (챗봇이 고객 언어로 옮긴다)
REASONS = {
    "customer_unresolved": "Since this wasn't resolved, we'll pass it to a support engineer.",
    "remote_retries": (
        "The same problem came back after remote troubleshooting, "
        "so a support engineer needs to check it."
    ),
    Category.QUOTE: "A quotation has to be issued by our sales team.",
    Category.ORDER_LEAD: "A delivery date has to be confirmed by our order team.",
    Category.WARRANTY: "Warranty approval has to be decided by our support team.",
    Category.RETURN: "Return approval has to be decided by our support team.",
    "no_evidence": "We couldn't find this in our documents, so a support engineer will answer.",
}


@dataclass
class HandoffDecision:
    handoff: bool
    reason: str = ""
    code: str = ""  # 어느 조건으로 넘겼는지 (기록·통계용)


def should_handoff(
    category: Category | None,
    best_score: float,
    customer_unresolved: bool = False,
    remote_attempts: int = 0,
    decision_requested: bool = True,
) -> HandoffDecision:
    """위 전환 조건을 순서대로 본다.

    best_score 는 **제품 필터 없이** 검색한 docs 1등 점수(근거가 없으면 0.0). 기준값을 그렇게
    쟀기 때문에, where={"product_code": …} 로 거른 결과의 점수를 넘기면 안 된다 (CSA-32).
    remote_attempts 는 챗봇이 안내한 원격 조치가 실패(재발)한 횟수.
    decision_requested=False 면 결정 유형이어도 정보만 묻는 말이다 (보증 기간·표준 납기 …) → 결정
    조건으로 넘기지 않는다. 챗봇이 Jev 로 가른다 (chatbot/agent.py).
    """
    if customer_unresolved:
        return _handoff("customer_unresolved")
    if (
        category
        and BUNDLE_OF.get(category) == Bundle.DIAGNOSIS
        and MAX_REMOTE_RETRIES is not None
        and remote_attempts >= MAX_REMOTE_RETRIES
    ):
        return _handoff("remote_retries")
    if category in DECISION_CATEGORIES and decision_requested:
        return _handoff(category)
    if MIN_RETRIEVAL_SCORE is not None and best_score < MIN_RETRIEVAL_SCORE:
        return _handoff("no_evidence")
    return HandoffDecision(handoff=False)


def _handoff(key: str | Category) -> HandoffDecision:
    code = f"decision_{key.value.lower()}" if isinstance(key, Category) else key
    return HandoffDecision(handoff=True, reason=REASONS[key], code=code)
