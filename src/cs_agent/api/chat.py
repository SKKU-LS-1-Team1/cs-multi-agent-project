# 고객 챗봇 API (CSA-32 · 담당 조수빈)
#
# router = APIRouter(prefix="/chat")
# - POST /api/chat   ChatIn → ChatOut  (chatbot/agent.py 의 모델)
#   1. sessions.history(session_id) 로 지난 대화를 읽는다 (cache/store.py, CSA-45)
#   2. chatbot.agent.respond(body, history, docs, llm)
#   3. sessions.append(session_id, 고객 메시지, 답변)
#   응답에 화면 이동 지시(navigation)와, 전환 시 문의서 초안(form)이 담긴다 → 고객 화면 CSA-38 이
#     쓴다.
