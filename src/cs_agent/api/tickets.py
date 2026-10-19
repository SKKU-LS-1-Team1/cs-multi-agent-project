# 문의 접수 · 조회 · 상담원 처리 API (CSA-21 · CSA-25 · CSA-40 · 담당 김동규)
#
# router = APIRouter(prefix="/tickets"), main.py 에서 "/api" 아래 등록. 일은 services/tickets.py
#   가 한다.
#
# 만들 엔드포인트
# - POST /api/tickets                    InquiryIn → TicketOut   문의 접수 → 그래프 실행
#     (고객 문의하기 화면 CSA-39, mock 데이터 CSA-23, 평가 스크립트 CSA-50 이 쓴다)
# - GET  /api/tickets?dept=              → list[dict]            상담원 작업 목록 (SLA 순, 75%
#     경고, CSA-40)
# - GET  /api/tickets/{ticket_id}        → TicketOut             검토 화면 (초안·근거·점검 결과,
#     CSA-41·42)
# - POST /api/tickets/{ticket_id}/action ReviewIn → TicketOut    승인·수정 후 승인·AI
#     재작성·추가정보 요청·
#                                                                이관·반려 (CSA-25)
# - POST /api/tickets/{ticket_id}/resolve → TicketOut            해결 확정 → 사례 DB 저장 (기획서
#     7.1)
# 없는 ticket_id 는 404.
