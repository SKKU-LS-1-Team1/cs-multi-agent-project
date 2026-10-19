"""고객 챗봇 API (CSA-32 · CSA-38). 응답에 화면 이동 지시와 문의서 초안이 담긴다."""

from fastapi import APIRouter

from cs_agent.api.deps import LLM, ChatSessions, Docs
from cs_agent.chatbot.agent import ChatIn, ChatOut, respond

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatOut)
def chat(body: ChatIn, sessions: ChatSessions, docs: Docs, llm: LLM) -> ChatOut:
    history = sessions.history(body.session_id)
    out = respond(body, history, docs, llm)
    sessions.append(body.session_id, body.message, out.answer)
    return out
