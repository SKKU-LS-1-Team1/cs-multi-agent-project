# FastAPI 진입점 (CSA-21 · 담당 김동규 · Sprint 1)
# 실행: uv run uvicorn cs_agent.main:app --reload  → http://localhost:8000/docs
#
# 할 일
# 1. create_app(): FastAPI 앱을 만들고 공유 객체를 app.state 에 둔다.
#    - app.state.llm = llm.router.get_router()
#    - app.state.docs, cases = agents.retrieval.default_retrievers()
#    - app.state.tickets = services.tickets.TicketService(...)
#    - app.state.chat_sessions = cache.store.ChatSessionStore()
# 2. GET /api/health → {"status": "ok", "version": ...}
# 3. 라우터 등록 (모두 prefix "/api"): api/tickets.py, api/chat.py, api/products.py,
#      api/dashboard.py
#    Nginx(infra/nginx/nginx.conf)가 /api 요청을 이 앱으로 넘긴다.
# 4. 시작 시 DB 테이블 확인(db/session.py), 기준표 로드(rules/tables.py)
# 5. 모듈 끝에 app = create_app()  (Dockerfile CMD 가 cs_agent.main:app 을 띄운다)
