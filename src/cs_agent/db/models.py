# PostgreSQL 스키마 (CSA-24 · 담당 조수빈 · Sprint 1)
#
# SQLAlchemy 2.0 선언형(Mapped, mapped_column)으로 쓴다. 다 만들면 김동규 님(승인 API CSA-25)과
# 박종석 님(SQL CSA-20)에게 알린다. 그래프 체크포인트 테이블은 langgraph-checkpoint-postgres 가
#   따로 만든다.
#
# 만들 테이블 (기획서 6장·7장·7.1, schemas.py 의 필드와 이름을 맞춘다)
# 1. tickets — 문의 1건
#    ticket_id(PK), channel, customer_id, customer_tier, language, subject, body,
#    category, category_confidence, product_code, error_code, urgency_flag,
#    priority, priority_rule_id, assigned_dept, routing_rule_id, escalated_to, missing_info(JSON),
#    status(domain.TicketStatus), followups(재문의 횟수), customer_wait_hours(SLA 정지 시간 누적),
#    sla_first_response_target_h, sla_resolution_target_h, received_at, resolved_at
# 2. drafts — 추천 답변 버전마다 1행 (재작성 포함)
#    id, ticket_id(FK), version, kind(draft | info_request), text, template,
#    evidence(JSON: doc_id·section·score), checks(JSON: 자동 점검 결과), model, created_at
# 3. reviews — 상담원 처리 기록
#    id, ticket_id(FK), draft_id(FK), action(domain.ReviewAction), reviewer, edited_text,
#    feedback(한 줄), feedback_reason(domain.FeedbackReason 4개), escalated_to, created_at
#    → 그대로 승인 시각 / 원본·수정본·수정 사유 / 반려 사유가 모두 여기서 나온다
# 4. chat_sessions, chat_messages — 챗봇 대화 기록 (문의로 전환되면 ticket_id 연결)
#    chat_messages.navigation(JSON) 에 화면 이동 지시를 남긴다
# 5. resolution_cases — 해결 사례 (원본 + 벡터를 같은 행에)
#    case_id, ticket_id, category, product_code, error_code, summary, cause, action_taken,
#    final_reply, reference_doc_id, feedback_reason, data_split(train | live), created_at,
#    embedding(Vector(settings.embedding_dim)), text_hash,
#    searchable(bool, 재문의로 다시 열리면 false)
# 6. doc_chunks — 공식 문서·FAQ·정책의 절 단위 조각 + 벡터 (CSA-18 이 채운다)
#    id("doc_id#section", PK), doc_id, section, title, doc_type, product_code, family, text,
#    text_hash, embedding(Vector(settings.embedding_dim))
#
# 벡터 검색 (pgvector, 팀장 확정: ChromaDB 대신)
# - from pgvector.sqlalchemy import Vector (extra: rag). 차원은 settings.embedding_dim(1536).
# - Alembic 첫 리비전 맨 앞에 op.execute("CREATE EXTENSION IF NOT EXISTS vector").
# - doc_chunks.embedding, resolution_cases.embedding 에 HNSW 인덱스 (vector_cosine_ops).
#   2000차원 넘으면 인덱스를 못 건다 → 그래서 1536.
#
# 할 일
# 1. 위 테이블을 클래스로 만든다 (Base 상속). 상태·행동 값은 domain.py 의 Enum 값을 문자열로 저장.
# 2. 작업 목록(SLA 순)·부서 대시보드 조회용 인덱스: tickets(status, assigned_dept),
#      tickets(received_at). 벡터 HNSW 인덱스는 위 '벡터 검색' 참고.
# 3. Alembic 마이그레이션 추가 (alembic init, 첫 리비전).
#
# 만들 것 (이름·모양은 다른 파일이 이대로 부른다)
#
#   class Base(DeclarativeBase):
#       pass
