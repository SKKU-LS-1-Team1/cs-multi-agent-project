# 고객 챗봇 API (CSA-32 · 담당 조수빈)
#
# main.py 에서 "/api" 아래 등록.
# - POST /api/chat   ChatIn → ChatOut  (chatbot/agent.py 의 모델)
#   1. sessions.history(session_id) 로 지난 대화를 읽는다 (cache/store.py, CSA-45)
#   2. chatbot.agent.respond(body, history, docs, llm)
#   3. sessions.append(session_id, 고객 메시지, 답변)
#   응답에 화면 이동 지시(navigation)와, 전환 시 문의서 초안(form)이 담긴다 → 고객 화면 CSA-38 이
#     쓴다.
# - LLM 분당 호출 상한에 걸리면 429, 그 밖의 모델 호출 실패는 그대로 500 이다. 이때는 대화를
#   저장하지 않는다 (고객이 같은 말을 다시 보내면 된다).
from fastapi import APIRouter, HTTPException

from cs_agent.api.deps import LLM, ChatSessions, Docs
from cs_agent.chatbot.agent import ChatIn, ChatOut, respond
from cs_agent.llm.router import RateLimited

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatOut)
def chat(body: ChatIn, sessions: ChatSessions, docs: Docs, llm: LLM) -> ChatOut:
    history = sessions.history(body.session_id)
    try:
        out = respond(body, history, docs, llm)
    except RateLimited as e:
        raise HTTPException(429, str(e)) from e
    sessions.append(body.session_id, body.message, out.answer)
    return out
