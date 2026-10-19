# Langfuse 기록 (CSA-48 · 담당 김동규 · Sprint 1)
#
# 모든 LLM 호출을 남긴다. K1(처리 지연 p95)과 Jev·Gemini 비교(기획서 9.2)를 이 기록으로 잰다.
#
# 할 일
# 1. trace(task, model, prompt, **metadata): with 문으로 감싸는 컨텍스트 매니저.
#    종료 시 Langfuse에 generation(name=task, model, input, output, latency) 을 남긴다.
# 2. 키(settings.langfuse_public_key / secret_key)가 없으면 아무것도 하지 않는다.
# 3. 문의 1건의 노드 실행 전체를 하나의 trace 로 묶는다 (ticket_id = trace id).
#    LangGraph 콜백(langfuse.callback.CallbackHandler)을 graph.invoke config 에 넣는 방법도 검토.
# 4. 모델 이름·토큰·비용을 남겨 단계별 비용 비교가 되게 한다.
#
# 만들 것 (이름·모양은 다른 파일이 이대로 부른다)
#
#   @dataclass
#   class Span:
#       task: str
#       model: str
#       prompt: str
#       output: Any = None
#       metadata: dict[str, Any] = field(default_factory=dict)
#
#   @contextmanager
#   def trace(task: str, model: str, prompt: str, **metadata: Any) -> Iterator[Span]:
