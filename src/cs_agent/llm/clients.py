# 모델별 클라이언트 (CSA-48 · 담당 김동규)
#
# 할 일
# 1. JevClient: TypeSafe AI의 판단 전용 모델. DigitalOcean 서버리스 추론 API(settings.jev_base_url,
#    요청당 과금)로 부른다. 정해진 보기(options) 안에서 답과 확신도만 돌려받는다.
#    요청·응답 형식은 얼리 액세스 문서 기준으로 맞춘다.
# 2. GeminiClient: langchain-google-genai 의 ChatGoogleGenerativeAI (extra: llm).
#    write() = 문장 작성, judge() = 보기 중 하나를 JSON으로 받기 (Jev 대체용).
# 3. 타임아웃·재시도(429·5xx) 정책을 정한다. 지연 목표 K1 p95 ≤ 60초.
#
# 만들 것 (이름·모양은 다른 파일이 이대로 부른다)
#
#   @dataclass
#   class Judgement:
#       answer: str  # options 중 하나
#       confidence: float  # 0~1
#       model: str
#
#   class Judge(Protocol):
#       name: str
#
#       def judge(self, prompt: str, options: list[str]) -> Judgement: ...
#
#   class Writer(Protocol):
#       name: str
#
#       def write(self, prompt: str) -> str: ...
