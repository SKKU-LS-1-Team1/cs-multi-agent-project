# FastAPI 의존성 (CSA-21 · 담당 김동규)
#
# 요청마다 app.state 의 공유 객체를 꺼내 라우터에 넘긴다 (main.py 가 만들어 둔다).
# ruff B008 규칙 때문에 기본값에 Depends() 를 쓰지 말고 Annotated 로 만든다:
#   Tickets      = Annotated[TicketService, Depends(lambda request: request.app.state.tickets)]
#   ChatSessions = Annotated[ChatSessionStore, Depends(... .chat_sessions)]
#   Docs         = Annotated[Retriever, Depends(... .docs)]
#   LLM          = Annotated[LLMRouter, Depends(... .llm)]
# DB 세션(db/session.py)도 여기서 의존성으로 만든다 (CSA-24).
