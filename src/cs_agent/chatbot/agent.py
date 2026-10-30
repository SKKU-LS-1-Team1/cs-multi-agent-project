# 챗봇 대화 에이전트 (CSA-32 · 담당 조수빈 · Sprint 2)
#
# api/chat.py 의 POST /api/chat 이 부른다. 대화 기록은 cache/store.py 의 ChatSessionStore(Redis)에
#   있다.
#
# 할 일
# 1. respond(): 대화 기록 + 새 메시지로 InquiryIn 을 만들고 (viewing_product 를 product_code 로),
#    문의 분석(agents/analysis.py)으로 유형·제품·에러코드를 뽑는다. 새로 만들지 말고 재사용한다.
# 2. 지식 검색(agents/retrieval.py)으로 근거를 찾는다. 제품을 알면 where={"product_code": …}.
# 3. 화면 이동(chatbot/navigation.py decide)을 정한다.
# 4. 문의 전환(chatbot/handoff.py should_handoff)이면: 이유 한 줄 + "문의하기로 이동" 답변,
#    handoff=True, form=fill_form(...) (chatbot/form_filler.py).
# 5. 아니면 Gemini로 고객 언어 답변: llm.write("chat_answer", …). 공개 문서 근거 안에서만 답한다.
#    견적 금액 확정·보증 승인·원인 단정은 하지 않는다.
# 6. 유형별 필수 항목 중 아직 안 나온 것 1~2개를 ask_fields 에 넣어 미리 묻는다 (예: 불량 → 시리얼).
#    필수 항목 목록은 rules/engine.py required_info().
# 7. 대화 의도·재문의·해결 여부 판단은 Jev(llm.judge)로 (기획서 9.2).
#
# 완료 기준: 기획서 5.4·5.5 시나리오(S100 E.OC → 고장 탭 → 재발 → 문의하기 자동 채움)가 끝까지 동작
#
# 참고: 기획서 v10 5장
#
# 구현 메모
# - history 는 ChatSessionStore 의 기록(고객, 챗봇, 고객 … 순서)이다. 분석(analysis.py)은 역할이
#   붙은 대화를 받으므로 짝수 번째를 user, 홀수 번째를 assistant 로 바꿔서 넘긴다. 기록이 홀수 개면
#   (오래된 쪽이 잘려 나간 경우) 맨 앞 하나를 버려 순서를 맞춘다.
# - 문의 전환의 best_score 는 제품 필터 없이 찾은 docs 1등 점수여야 한다(handoff.py 기준값을 그렇게
#   쟀다). 그래서 답변 근거와 따로 한 번 더 찾는다. 검색기가 없으면 근거 없음(0.0)으로 본다.
#   로컬 키워드 검색(KeywordRetriever)의 점수는 척도가 달라 기준값(0.70)과 비교할 수 없다. pgvector
#   검색일 때만 믿을 수 있다.
# - 재발 횟수(remote_attempts)와 "해결 안 됐다 · 상담원 연결" 요청은 Jev 판단(llm.judge)으로 센다.
#   진단형(불량·설치·펌웨어)일 때만 지난 고객 말을 다시 판단하고, 판단은 라우터 캐시에 남는다.
#   Jev 가 꺼져 있으면(fake) 판단하지 않은 것으로 본다.
# - 분석이 실패하면(AnalysisError) 분류 없이 계속한다: 화면은 옮기지 않고, 대시보드에서 보던
#   제품으로 검색·답변한다. 분류가 없으면 문의서 초안(form)도 만들 수 없다.
# - 고객 언어: ChatIn.language 가 있으면 그것, 없으면 고객 말에서 감지한다 (화면은 보내지 않는다).
#   감지하지 못하면 영어.
# - 응답 시간: LLM 추출(Gemini 구조화 추출)은 한 번에 10초 넘게 걸린다. 그래서 분류 직후 뒤에서
#   돌리고(_POOL), 그동안 규칙 추출(제품·에러코드·시리얼, LLM 없이 즉시)로 검색·전환 판단·답변을
#   만든다. 답변을 다 쓴 뒤 LLM 추출을 EXTRACT_GRACE_S 만 더 기다려, 끝났으면 그 결과로 화면 이동·
#   ask_fields 를 정하고 아니면 규칙 추출로 정한다 (대화 1턴 ≈ 답변 작성 시간). 문의 전환일 때만
#   문의서를 채우려고 끝까지 기다린다. 추출이 실패하면 규칙 추출로 계속한다.
# - 전환 안내는 고객 언어로 옮기고 그 언어로 확인될 때만 쓴다 (info_request.in_language). 최대
#   HANDOFF_TRANSLATE_ATTEMPTS 번 다시 옮기고(캐시를 지우고), 끝내 안 되거나 LLM 이 꺼져 있으면
#   언어별 고정 문장(HANDOFF_FALLBACK)을 쓴다. 비영어 고객에게 영어 문장을 그대로 보내지 않는다.
#   handoff_reason 은 기록·상담원용 영어 이유다 (고객에게는 answer 가 보인다).
# - 안전 신호(연기·화재·감전)는 여기서 따로 막지 않는다. 필요하면 handoff 조건에 더한다.
# - 아직 구체적인 질문이 없는 말("UPS 에 대해 궁금한 점이 있어요", 인사)은 검색 1등 점수가 낮아
#   '근거 없음'(handoff.py MIN_RETRIEVAL_SCORE)에 걸린다. 그 기준값은 실제 질문과 범위 밖 질문으로만
#   쟀으므로, Jev 가 GENERAL 로 본 말은 근거 없음으로 넘기지 않고 무엇이 궁금한지 되묻는다.
#   (해결 안 됨·상담원 요청·재발·결정 유형 전환은 그대로)
# - 결정 유형(견적·납기·보증·반품)이어도 정보만 묻는 말(보증 기간, 표준 납기, 반품 정책 …)은 문서로
#   답한다. 결정이 필요한지(이 수량 견적 발행·납기 확약·내 제품 보증 수리/교체 승인·반품 승인)는
#   Jev 가 가른다 (DECISION_PROMPT). Jev 가 꺼져 있거나 판단이 안 되면 결정 필요로 본다
#   (전처럼 넘긴다).
# - 결정 유형 전환일 때도 답할 수 있는 나머지 질문(정격 용량 …)은 버리지 않는다: 문서로 그 부분을
#   답하고, 결정이 필요한 부분은 문의서로 넘긴다고 덧붙인다 (PARTIAL_PROMPT). 문의서도 같이 연다.
#   답변을 못 쓰면 전처럼 전환 안내만 보낸다.
# - 근거 없음 판단 점수 (2026-10-23 운영 사고: "UPS 보증기간…" 다음 "인버터 E.OC" 가 상담원으로 감)
#   · 최근 고객 말을 합친 검색과 지금 말만의 검색 중 높은 점수를 쓴다. 대화 중 주제가 바뀌면 합친
#     검색어는 두 주제를 다 담은 조각이 없어 점수가 떨어진다.
#   · 기준값은 pgvector 코사인 점수로만 쟀다. 키워드 검색(임베딩이 적재되지 않은 서버의 대체
#     구현)은 점수 척도가 달라(calibrated=False) '찾았는지'만 본다: 지금 말, 합친 말, 지금 말 +
#     대화의 제품 코드 중 하나라도 걸리면 근거 있음. 키워드 검색은 한국어 낱말을 못 찾으므로 제품
#     코드를 붙여 찾는다 (근거 조각도 같은 방식으로 더 찾는다).
# - 우리 제품 이야기(제품·제품군·고장 카탈로그 에러코드가 나옴)면 근거 없음으로 넘기지 않는다.
#   기준값 0.70 은 긴 티켓 본문으로 쟀고, 짧은 채팅 말은 맞는 문서를 찾아도 점수가 낮다
#   (2026-10-23 pgvector 측정: "인버터가 E.OC 에러로 멈췄어요." 0.693 TG E.OC 절, "S100 보증기간이
#   얼마나 되나요?" 0.601 FAQ 보증 답 — 범위 밖 "XYZ-9000 위성용 배터리" 0.587, "냉장고가
#   고장났어요" 0.541 와 겹친다). 점수로는 짧은 말의 범위를 가를 수 없으므로, 범위 안이면 문서·
#   제품 정보·정책으로 답하고 정말 없으면 답변이 그렇다고 말한다 (고객은 '해결 안 됐어요'로 넘긴다).
#   범위 밖 말(제품 이름이 없음)만 기준값으로 넘긴다.
# - 답변 프롬프트에는 문서 근거 말고도 기준표의 제품 정보(보증 기간·표준 납기·최소 주문 수량·
#   규격·인증, 가격은 빼고)와 유형별 정책 문서(보증·반품·주문, POLICY_DOCS) 전체를 넣는다.
#   "보증기간 얼마예요?" 같은 기본 질문은 검색 결과와 상관없이 답할 수 있어야 한다.
# - 제품군 이름(무정전전원장치·태양광·인버터 …)은 규칙 추출이 모델명만 찾아서 놓친다. 그래서
#   FAMILY_TERMS 로 제품군을 찾아 채운다 → 화면은 FAMILY_ONLY("제품 선택" 버튼), 답변은 그 제품군
#   제품 목록을 맥락으로 쓴다. 여러 제품군에 걸리면 가장 긴 낱말이 이기고, 같은 길이로 갈리면
#   비운다.
# - 제품 이름을 잘못 쓴 말("인터버 종류 뭐있어?")은 FAMILY_TERMS·규칙 추출에 안 걸려 범위 밖으로
#   보이고 근거 없음으로 넘어갔다 (2026-10-30). LLM 추출도 모델명이 없으면 제품군을 비운다. 그래서
#   근거 없음으로 넘기기 직전에만 Jev 에게 우리 제품 이야기인지 묻는다 (OUR_PRODUCT_PROMPT, 판단이
#   안 되면 넘긴다). 그렇다면 넘기지 않고, 제품군을 모르니 답변 프롬프트에 전체 제품 목록을 넣어
#   Gemini 가 고르게 한다. Jev 에게 제품군을 고르게 하면 "인터버"를 태양광(PV)으로 고르기도 해서
#   범위 판단에만 쓴다. (2026-10-30 Jev 측정: 오타·제품군 이름 8개 YES, 날씨·냉장고·XYZ-9000·
#   LG 에어컨 인버터·아이폰 5개 NO. 대개 0.2초, Jev 가 확신이 없어 Gemini 로 넘어가면 3~11초 —
#   넘기려던 말에서만 묻는다.)
# - Jev 가 우리 제품 이야기가 아니라고 하면(날씨·남의 제품 …) 상담원에게 넘기지 않고 "문의주신
#   정보는 제공되지 않습니다"라고 답한다 (DECLINE_ANSWER, 고객 언어 고정 문장). 엔지니어가 답할 일이
#   아니다. Jev 가 판단하지 못했을 때만 전처럼 근거 없음으로 넘긴다. 제품 이야기를 하던 대화 중에
#   엉뚱한 말이 오면 대화의 제품 때문에 범위 안으로 보이므로, 답변 프롬프트에도 같은 문장으로
#   답하라고 적는다 (Jev 를 매번 부르지 않는다).
# - 답변 모양: 좁은 채팅 창에서 읽기 쉽게 첫 줄에 바로 답하고, 여러 제품·값은 "- " 목록, 단계는
#   "1. " 목록, 핵심 값·제품명·에러코드만 **굵게**, 근거는 줄 끝에 [문서 · 절] 로 단다
#   (CHAT_PROMPT). 화면(home/components/ChatText.jsx)이 굵게 · 목록 · [문서 · 절] 만 그리므로
#   제목·코드 표시 등 나머지 마크다운은 _chat_text 가 걷어 낸다.
import logging
import re
from concurrent.futures import Future, ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout

from pydantic import BaseModel, Field

from cs_agent.agents.analysis import AnalysisError, classify, extract, extract_details
from cs_agent.agents.info_request import in_language, language_name
from cs_agent.agents.retrieval import (
    Retriever,
    doc_sections,
    finalize_evidence,
    find_error_codes,
    first_pass,
)
from cs_agent.chatbot.form_filler import InquiryDraftForm, fill_form
from cs_agent.chatbot.handoff import DECISION_CATEGORIES, HandoffDecision, should_handoff
from cs_agent.chatbot.navigation import Navigation, decide
from cs_agent.domain import BUNDLE_OF, Bundle
from cs_agent.llm.router import LLMRouter, RateLimited
from cs_agent.rules.engine import UNKNOWN_PRODUCT_FIELD, required_info
from cs_agent.rules.tables import RefTables, load_tables
from cs_agent.schemas import Classification, Evidence, Extraction, InquiryIn

_LOGGER = logging.getLogger(__name__)

CHANNEL = "CHAT"
ASK_FIELDS_MAX = 2  # 한 번에 미리 묻는 필수 항목 수
QUERY_MESSAGES = 3  # 검색어로 쓰는 최근 고객 말 수
INTENT_HISTORY = 4  # 재발을 다시 판단하는 지난 고객 말 수
EVIDENCE_CHARS = 1500  # 근거 한 개당 프롬프트에 넣는 글자 수
EXTRACT_WAIT_S = 70.0  # 문의 전환 때 LLM 추출 대기 상한 (analysis.py 추출 예산 60초 + 여유)
EXTRACT_GRACE_S = 2.0  # 답변을 다 쓴 뒤 LLM 추출을 더 기다리는 시간 (전환이 아닐 때)
HANDOFF_TRANSLATE_ATTEMPTS = 3

_POOL = ThreadPoolExecutor(max_workers=8, thread_name_prefix="chat-extract")

# 유형별로 늘 함께 보는 정책 문서 (data/raw/docs/policy, 각 2KB 안팎)
POLICY_DOCS = {
    "WARRANTY": "POL-WARRANTY",
    "RETURN": "POL-RETURN",
    "ORDER_LEAD": "POL-ORDER",
    "QUOTE": "POL-ORDER",
}
FAMILY_FACTS_MAX = 4  # 제품군만 알 때 제품 정보를 넣는 제품 수
# 답변 근거 절 수. 한 말에 질문이 둘이면(보증 기간 + 정격 용량) 3개로는 한쪽 절이 잘린다.
CHAT_EVIDENCE_K = 5

RECURRENCE, REQUEST_AGENT, GENERAL, OTHER = "RECURRENCE", "REQUEST_AGENT", "GENERAL", "OTHER"
INTENT_OPTIONS = [RECURRENCE, REQUEST_AGENT, GENERAL, OTHER]

# 제품군을 가리키는 말 (고객 화면 제품군 이름 + 영어·일본어·중국어 흔한 이름). 소문자로 비교한다.
# 영문 낱말은 앞뒤가 영문·숫자가 아닐 때만, 나머지는 띄어쓰기를 빼고 찾는다. "pcs" 는 수량(20 pcs)과
# 겹쳐서 넣지 않는다 (PCS 모델명은 규칙 추출이 찾는다).
FAMILY_TERMS: dict[str, tuple[str, ...]] = {
    "LV_BREAKER": (
        "저압차단기",
        "차단기",
        "배선용차단기",
        "누전차단기",
        "기중차단기",
        "mccb",
        "acb",
        "elcb",
        "circuit breaker",
        "breaker",
        "遮断器",
        "断路器",
    ),
    "MV_EQUIP": (
        "고압전력기기",
        "고압차단기",
        "진공차단기",
        "배전반",
        "수배전반",
        "개폐기",
        "vcb",
        "switchgear",
        "vacuum circuit breaker",
        "medium voltage",
        "配電盤",
        "开关柜",
    ),
    "TRANSFORMER": ("변압기", "트랜스", "transformer", "変圧器", "变压器"),
    "METER": (
        "전력계측기",
        "계측기",
        "전력량계",
        "전력미터",
        "power meter",
        "energy meter",
        "電力量計",
        "电能表",
        "电表",
    ),
    "CONTROL": (
        "제어기",
        "전자접촉기",
        "접촉기",
        "마그네트",
        "과부하계전기",
        "열동계전기",
        "계전기",
        "contactor",
        "overload relay",
        "電磁接触器",
        "接触器",
        "继电器",
    ),
    "DRIVE": (
        "인버터",
        "드라이브",
        "inverter",
        "vfd",
        "variable frequency drive",
        "インバータ",
        "变频器",
    ),
    "PLC": ("plc", "피엘씨", "programmable logic controller"),
    "HMI": (
        "hmi",
        "터치패널",
        "운전패널",
        "touch panel",
        "operator panel",
        "タッチパネル",
        "触摸屏",
    ),
    "ESS": ("에너지저장장치", "에너지저장", "ess", "energy storage", "bms", "蓄電システム", "储能"),
    "PV": (
        "태양광",
        "태양광인버터",
        "솔라인버터",
        "솔라",
        "solar",
        "solar inverter",
        "pv",
        "pv inverter",
        "photovoltaic",
        "太陽光",
        "太陽光インバータ",
        "逆变器",
        "光伏",
    ),
    "UPS": ("무정전전원장치", "무정전", "ups", "uninterruptible power", "無停電電源", "不间断电源"),
}

INTENT_PROMPT = """Classify the customer's latest message in a support chat.

RECURRENCE: the customer says the problem happened again or still continues after trying the
assistant's earlier advice.
REQUEST_AGENT: the customer says the problem is not solved, or asks to talk to a person or to
submit an inquiry.
GENERAL: a greeting, or the customer only names a product, product line or topic, or says they
have a question, without asking anything specific yet (e.g. "I have a question about your UPS").
OTHER: anything else, including a specific new question.

Assistant's previous advice:
{advice}

Customer's latest message:
{message}
"""

CHAT_PROMPT = """You are the customer-support chatbot of an industrial electrical equipment maker.
Answer the customer's latest message in {language}.

Rules:
- If the latest message is not about our products or their use at all (for example the weather,
  news or another company's product), reply with exactly this text and nothing else:
  {decline}
- Use ONLY the reference documents below. If they do not contain the answer, say you could not
  find it and that a support engineer can help.
- If the customer has not asked a specific question yet (a greeting, only a product or topic
  name, or "I have a question"), do not say you could not find anything. In one or two
  sentences say what you can help with for the product(s) below (specifications, installation,
  error codes, firmware, warranty, manuals) and ask what they would like to know. If several
  products are listed and none is chosen, ask which one.
- Never confirm a quotation amount, approve a warranty or a return, or state a definite root cause.
  Offer to open the inquiry form instead.
- Be concise. Answer directly in the first sentence.
- Format for a narrow chat window:
  - Put several products, values or options on separate lines starting with "- ", and steps
    on numbered lines ("1. ", "2. "). One item per line. Leave a blank line before and after
    a list.
  - Make only key values, product names and error codes **bold**. No headings, tables, code
    or any other Markdown.
  - When you use a document section, put its label exactly as in the reference documents, such
    as [TG-S100 · 3.1 E.OC], at the very end of that line, after the final punctuation.
- Do not repeat steps the assistant already advised earlier in the conversation. Build on them.

Product: {product}
Inquiry type: {category}

Reference documents:
{evidence}

Conversation so far:
{conversation}

Customer's latest message:
{message}
"""

DECISION, INFO = "DECISION", "INFO"
DECISION_PROMPT = """A customer of an industrial electrical equipment maker wrote the message below.
Does it ask the company to make a decision or a commitment that a chatbot must not make?

DECISION: asks to issue a quotation or price for specific items or quantities, to confirm or
promise a delivery date, to approve warranty service (repair, replacement, refund) for their
unit, or to approve a return.
INFO: only asks for general information the documents can answer, such as the warranty period,
the standard lead time, the return policy or specifications, possibly with other questions.

Customer's message:
{message}
"""

YES, NO = "YES", "NO"
OUR_PRODUCT_PROMPT = """A customer wrote the message below to the support chat of an industrial
electrical equipment maker. Is the customer asking about our products listed below? The customer
may misspell product names.

YES: the message is about one of these products or product families.
NO: the message is about something else, such as another company's product or an unrelated topic.

Our products:
{products}

Customer's recent messages (latest last):
{message}
"""

PARTIAL_PROMPT = """

Part of this message needs a decision by our team: {reason}
- Answer only the OTHER questions in the message, from the reference documents, as usual.
- Then add one sentence saying that the part needing a decision will be handled by our team
  through the inquiry form, which you are opening now. Do not decide or promise it yourself.
- If there is no other question, write only that sentence.
"""

TRANSLATE_PROMPT = """Translate the text into {language}. Output only the translation.

{text}
"""

HANDOFF_SUFFIX = " I'll open the inquiry form with what we've discussed so far."

# 전환 안내를 옮기지 못했을 때 쓰는 고정 문장. drafting._CUSTOMER_LANGUAGES 와 같은 언어
HANDOFF_FALLBACK = {
    "en": "A support engineer will take it from here."
    " I'll open the inquiry form with what we've discussed so far.",
    "ko": "담당 엔지니어가 이어서 도와드리겠습니다. 지금까지 나눈 내용으로 문의서를 열어 드릴게요.",
    "ja": "担当エンジニアが引き続き対応いたします。"
    "これまでの内容でお問い合わせフォームを開きます。",
    "zh": "将由技术支持工程师继续为您处理。我会根据目前的对话为您打开咨询表单。",
    "es": "Un ingeniero de soporte se encargará a partir de aquí."
    " Abriré el formulario de consulta con lo que hemos hablado hasta ahora.",
    "fr": "Un ingénieur support va prendre le relais."
    " J'ouvre le formulaire de demande avec ce que nous avons échangé jusqu'ici.",
    "de": "Ein Support-Techniker übernimmt ab hier."
    " Ich öffne das Anfrageformular mit dem, was wir bisher besprochen haben.",
    "it": "Un tecnico dell'assistenza proseguirà da qui."
    " Apro il modulo di richiesta con quanto discusso finora.",
    "pt": "Um engenheiro de suporte vai continuar a partir daqui."
    " Vou abrir o formulário de solicitação com o que conversamos até agora.",
    "ru": "Дальше вам поможет инженер службы поддержки."
    " Я открою форму обращения с тем, что мы уже обсудили.",
    "tr": "Bundan sonra bir destek mühendisi yardımcı olacak."
    " Şimdiye kadar konuştuklarımızla talep formunu açıyorum.",
    "pl": "Dalej zajmie się tym inżynier wsparcia."
    " Otworzę formularz zgłoszenia z tym, co do tej pory ustaliliśmy.",
    "vi": "Kỹ sư hỗ trợ sẽ tiếp tục giúp bạn."
    " Tôi sẽ mở biểu mẫu yêu cầu với những nội dung chúng ta đã trao đổi.",
    "id": "Teknisi dukungan akan melanjutkan dari sini."
    " Saya akan membuka formulir permintaan dengan apa yang sudah kita bahas.",
    "th": "วิศวกรฝ่ายสนับสนุนจะดูแลต่อจากนี้ ฉันจะเปิดแบบฟอร์มสอบถามพร้อมข้อมูลที่เราคุยกันไว้",
    "ar": "سيتولى مهندس الدعم متابعة طلبك من هنا. سأفتح نموذج الاستفسار بما ناقشناه حتى الآن.",
}

# 우리 제품 이야기가 아닌 말에 대한 안내 (위 메모). drafting._CUSTOMER_LANGUAGES 와 같은 언어
DECLINE_ANSWER = {
    "en": "Sorry, the information you asked about is not provided here."
    " Please ask about our products, such as specifications, installation, error codes,"
    " firmware, warranty or manuals.",
    "ko": "죄송합니다. 문의주신 정보는 제공되지 않습니다."
    " 저희 제품의 사양, 설치, 에러 코드, 펌웨어, 보증, 매뉴얼에 대해 문의해 주세요.",
    "ja": "申し訳ございません。お問い合わせの情報はご提供しておりません。"
    "当社製品の仕様、設置、エラーコード、ファームウェア、保証、マニュアルについてお問い合わせください。",
    "zh": "抱歉，我们不提供您所咨询的信息。"
    "请咨询我们产品的规格、安装、错误代码、固件、保修或手册。",
    "es": "Lo sentimos, aquí no ofrecemos la información que ha solicitado."
    " Consúltenos sobre nuestros productos: especificaciones, instalación, códigos de error,"
    " firmware, garantía o manuales.",
    "fr": "Désolé, les informations demandées ne sont pas fournies ici."
    " Interrogez-nous sur nos produits : caractéristiques, installation, codes d'erreur,"
    " firmware, garantie ou manuels.",
    "de": "Leider stellen wir die angefragten Informationen hier nicht bereit."
    " Fragen Sie uns gern zu unseren Produkten: technische Daten, Installation, Fehlercodes,"
    " Firmware, Garantie oder Handbücher.",
    "it": "Spiacenti, le informazioni richieste non sono disponibili qui."
    " Ci chieda dei nostri prodotti: specifiche, installazione, codici di errore, firmware,"
    " garanzia o manuali.",
    "pt": "Desculpe, as informações solicitadas não são fornecidas aqui."
    " Pergunte-nos sobre os nossos produtos: especificações, instalação, códigos de erro,"
    " firmware, garantia ou manuais.",
    "ru": "К сожалению, запрошенная информация здесь не предоставляется."
    " Задайте вопрос о нашей продукции: характеристики, монтаж, коды ошибок, прошивка,"
    " гарантия или руководства.",
    "tr": "Üzgünüz, sorduğunuz bilgi burada sağlanmıyor."
    " Ürünlerimizin teknik özellikleri, kurulumu, hata kodları, yazılımı, garantisi veya"
    " kılavuzları hakkında soru sorabilirsiniz.",
    "pl": "Przepraszamy, nie udostępniamy tutaj informacji, o które pytasz."
    " Zapytaj o nasze produkty: specyfikacje, instalację, kody błędów, oprogramowanie,"
    " gwarancję lub instrukcje.",
    "vi": "Xin lỗi, thông tin bạn hỏi không được cung cấp tại đây."
    " Vui lòng hỏi về sản phẩm của chúng tôi như thông số kỹ thuật, lắp đặt, mã lỗi,"
    " firmware, bảo hành hoặc tài liệu hướng dẫn.",
    "id": "Maaf, informasi yang Anda tanyakan tidak tersedia di sini."
    " Silakan tanyakan tentang produk kami, seperti spesifikasi, pemasangan, kode kesalahan,"
    " firmware, garansi, atau manual.",
    "th": "ขออภัย เราไม่ได้ให้ข้อมูลที่คุณสอบถามไว้ที่นี่"
    " กรุณาสอบถามเกี่ยวกับผลิตภัณฑ์ของเรา เช่น ข้อมูลจำเพาะ การติดตั้ง รหัสข้อผิดพลาด"
    " เฟิร์มแวร์ การรับประกัน หรือคู่มือ",
    "ar": "عذرًا، المعلومات التي طلبتها غير متوفرة هنا."
    " يمكنك السؤال عن منتجاتنا مثل المواصفات أو التركيب أو رموز الأخطاء أو البرامج الثابتة"
    " أو الضمان أو الأدلة.",
}


class ChatIn(BaseModel):
    session_id: str
    message: str
    language: str | None = None  # 없으면 고객 말에서 감지한다
    viewing_product: str | None = None  # 대시보드에서 보고 있는 제품 (양방향 연동)
    unresolved: bool = False  # 고객이 "해결 안 됐어요"를 누름


class ChatOut(BaseModel):
    answer: str
    navigation: Navigation
    evidence: list[Evidence] = Field(default_factory=list)
    ask_fields: list[str] = Field(default_factory=list)
    handoff: bool = False
    handoff_reason: str = ""
    form: InquiryDraftForm | None = None


def respond(
    chat: ChatIn,
    history: list[str],
    docs: Retriever | None,
    llm: LLMRouter,
    tables: RefTables | None = None,
) -> ChatOut:
    """대화 기록 + 새 메시지 → 챗봇 응답. 위 '할 일' 참고."""
    tables = tables or load_tables()
    history = history[len(history) % 2 :]  # 고객으로 시작하도록 맞춘다
    customer, advice = history[0::2], history[1::2]
    transcript = [
        {"role": "user" if i % 2 == 0 else "assistant", "content": m} for i, m in enumerate(history)
    ]
    viewing = chat.viewing_product if chat.viewing_product in tables.products else None
    language = _customer_language(chat, customer)
    inquiry = InquiryIn(channel=CHANNEL, language=language, body=chat.message, product_code=viewing)

    classification = _classify(inquiry, transcript, llm)
    category = classification.category if classification else None
    # LLM 추출은 뒤에서 돌리고, 그동안 규칙 추출로 검색·판단·답변을 만든다 (위 구현 메모)
    full = (
        _POOL.submit(_extract, inquiry, transcript, classification, llm, tables)
        if classification
        else None
    )
    said = [chat.message, *reversed(customer)]  # 제품군은 지금 말부터 찾는다
    quick = _with_family(
        _with_viewing(_rule_extraction(inquiry, transcript, category, tables), viewing, tables),
        said,
    )

    query = "\n".join([*customer[-(QUERY_MESSAGES - 1) :], chat.message])
    scope = " ".join(_scope_codes(quick, tables))  # 키워드 검색 보조 (위 메모)
    best_score = _best_score(docs, query, chat.message, scope)
    current, attempts = _intent_signals(chat, customer, advice, category, llm)
    decision = should_handoff(
        category,
        best_score,
        current == REQUEST_AGENT or chat.unresolved,
        attempts,
        decision_requested=_decision_requested(llm, chat.message)
        if category in DECISION_CATEGORIES
        else True,
    )
    in_scope = bool(quick.product_code or quick.product_family or find_error_codes(chat.message))
    # 제품 이름을 잘못 쓰면("인터버") 위에서 못 찾는다. 넘기기 직전에만 Jev 에게 묻는다 (위 메모)
    ours = (
        _about_our_products(llm, query, tables)
        if decision.code == "no_evidence" and current != GENERAL and not in_scope
        else None
    )
    if ours is False:
        # 우리 제품 이야기가 아니다 → 넘기지 않고 제공하지 않는 정보라고 답한다 (위 메모)
        return ChatOut(answer=_decline_answer(language), navigation=Navigation())
    misnamed = ours is True
    if decision.code == "no_evidence" and (current == GENERAL or in_scope or misnamed):
        # 질문 전이거나 우리 제품 이야기다 → 근거 없음으로 넘기지 않고 답한다 (위 메모)
        decision = HandoffDecision(handoff=False)

    candidates = first_pass(docs, None, query) if docs is not None else []
    if docs is not None and scope and not getattr(docs, "calibrated", False):
        candidates += first_pass(docs, None, f"{chat.message} {scope}")
    evidence = finalize_evidence(candidates, quick, k=CHAT_EVIDENCE_K, category=category)
    policy = doc_sections(POLICY_DOCS[category]) if category in POLICY_DOCS else []

    product_context = _product_context(quick, tables, whole_catalog=misnamed)
    prompt = CHAT_PROMPT.format(
        language=language_name(language),
        product=product_context,
        category=category or "unknown",
        evidence=_evidence_block(evidence, _product_facts(quick, tables), policy),
        conversation=_conversation(history) or "(first message)",
        message=chat.message,
        decline=_decline_answer(language),
    )

    if decision.handoff:
        # 추출을 기다리는 동안 안내를 쓴다. 결정 유형이면 답할 수 있는 나머지도 답한다 (위 메모)
        answer = (
            _partial_answer(prompt, decision.reason, llm)
            if decision.code.startswith("decision_")
            else None
        ) or _handoff_answer(decision.reason, language, llm)
        extraction = _with_family(_with_viewing(_joined(full, quick), viewing, tables), said)
        form = (
            fill_form(classification, extraction, [*history, chat.message], llm, tables)
            if classification
            else None
        )
        return ChatOut(
            answer=answer,
            navigation=_navigation(extraction, classification, tables),
            evidence=evidence,
            handoff=True,
            handoff_reason=decision.reason,
            form=form,
        )

    answer = _chat_text(llm.write("chat_answer", prompt))
    extraction = _with_family(
        _with_viewing(_joined(full, quick, EXTRACT_GRACE_S), viewing, tables), said
    )
    return ChatOut(
        answer=answer,
        navigation=_navigation(extraction, classification, tables),
        evidence=evidence,
        ask_fields=_ask_fields(
            extraction, category, extraction.product_code in tables.products, tables
        ),
    )


def _customer_language(chat: ChatIn, customer: list[str]) -> str:
    """ChatIn.language, 없으면 고객 말(지난 말 포함)에서 감지. 감지하지 못하면 영어."""
    if chat.language:
        return chat.language
    from cs_agent.agents.verification import detect_language

    return detect_language("\n".join([*customer, chat.message]))


def _classify(
    inquiry: InquiryIn, transcript: list[dict[str, str]], llm: LLMRouter
) -> Classification | None:
    """분류. 실패하면 분류 없이 계속한다 (화면은 옮기지 않고 보던 제품으로 답한다)."""
    try:
        return classify(inquiry, llm, transcript=transcript, include_secondary=False)
    except AnalysisError as e:
        _LOGGER.warning("챗봇 분류 실패 → 분류 없이 계속한다: %s", e)
        return None


def _extract(
    inquiry: InquiryIn,
    transcript: list[dict[str, str]],
    classification: Classification,
    llm: LLMRouter,
    tables: RefTables,
) -> Extraction:
    """LLM 추출 (_POOL 에서 돈다)."""
    return extract(
        inquiry, tables, llm=llm, transcript=transcript, category=classification.category
    )


def _rule_extraction(
    inquiry: InquiryIn, transcript: list[dict[str, str]], category, tables: RefTables
) -> Extraction:
    """LLM 없이 규칙으로만 찾은 값 (제품·에러코드·시리얼 …). 즉시 끝난다."""
    try:
        details = extract_details(
            inquiry, tables, llm=None, transcript=transcript, category=category
        )
    except Exception as e:  # 규칙 추출이 안 돼도 대화는 계속한다
        _LOGGER.warning("챗봇 규칙 추출 실패: %s", e)
        return Extraction(language=inquiry.language)
    return Extraction(
        product_code=details.product_code,
        product_family=details.product_family,
        error_code=details.error_code,
        fw_version=details.fw_version,
        serial_no=details.serial_no,
        language=inquiry.language,
        provided_info=list(details.provided_info),
        field_values=dict(details.fields),
    )


def _joined(full: Future | None, quick: Extraction, timeout: float = EXTRACT_WAIT_S) -> Extraction:
    """LLM 추출 결과. 없거나 timeout 안에 안 끝나거나 실패하면 규칙 추출."""
    if full is None:
        return quick
    try:
        extraction = full.result(timeout=timeout)
    except FutureTimeout:
        _LOGGER.info("챗봇 LLM 추출이 아직 안 끝남 → 이번 턴은 규칙 추출로")
        return quick
    except Exception as e:  # AnalysisError · 모델 오류
        _LOGGER.warning("챗봇 추출 실패 → 규칙 추출로 계속한다: %s", e)
        return quick
    return extraction.model_copy(update={"language": extraction.language or quick.language})


def _with_viewing(extraction: Extraction, viewing: str | None, tables: RefTables) -> Extraction:
    """제품을 못 찾았으면 대시보드에서 보던 제품이 대화의 맥락이다."""
    if extraction.product_code is not None or not viewing:
        return extraction
    return extraction.model_copy(
        update={
            "product_code": viewing,
            "product_family": extraction.product_family or tables.products[viewing].family,
        }
    )


def mentioned_family(texts: list[str]) -> str | None:
    """말에서 제품군 코드를 찾는다 (FAMILY_TERMS). 앞의 말부터 보고, 처음 걸린 말의 결과를 쓴다."""
    for text in texts:
        lower = text.lower()
        compact = re.sub(r"\s+", "", lower)
        hits: dict[str, int] = {}
        for family, terms in FAMILY_TERMS.items():
            for term in terms:
                if term.isascii():
                    found = re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", lower)
                else:
                    found = term.replace(" ", "") in compact
                if found:
                    hits[family] = max(hits.get(family, 0), len(term))
        if hits:
            longest = max(hits.values())
            best = [f for f, n in hits.items() if n == longest]
            return best[0] if len(best) == 1 else None
    return None


def _with_family(extraction: Extraction, texts: list[str]) -> Extraction:
    """제품도 제품군도 못 찾았으면 말에 나온 제품군 이름으로 채운다."""
    if extraction.product_code is not None or extraction.product_family:
        return extraction
    family = mentioned_family(texts)
    return extraction.model_copy(update={"product_family": family}) if family else extraction


def _product_context(extraction: Extraction, tables: RefTables, whole_catalog: bool = False) -> str:
    """답변 프롬프트의 Product 줄: 제품 이름, 제품군만 알면 그 제품군 제품 목록,
    우리 제품 이야기인데 제품군도 모르면(whole_catalog) 전체 제품 목록."""
    product = tables.products.get(extraction.product_code or "")
    if product:
        return product.name
    names = [p.name for p in tables.products.values() if p.family == extraction.product_family]
    if names:
        return f"not chosen yet; {extraction.product_family} products: " + ", ".join(names)
    if whole_catalog:
        return "not chosen yet; " + "; ".join(
            f"{family} products: " + ", ".join(names) for family, names in _families(tables).items()
        )
    return "unknown"


def _families(tables: RefTables) -> dict[str, list[str]]:
    """제품군별 제품 이름 (기준표 순서)."""
    families: dict[str, list[str]] = {}
    for p in tables.products.values():
        families.setdefault(p.family, []).append(p.name)
    return families


def _navigation(
    extraction: Extraction, classification: Classification | None, tables: RefTables
) -> Navigation:
    return decide(extraction, classification, tables) if classification else Navigation()


def _best_score(docs: Retriever | None, query: str, message: str, scope: str = "") -> float:
    """제품 필터 없이 찾은 docs 1등 점수. 검색기가 없거나 못 찾으면 0.0 (근거 없음).

    합친 최근 말(query)과 지금 말(message) 중 높은 점수. 기준값과 척도가 다른 검색기
    (calibrated=False)는 제품 코드(scope)를 붙여서도 찾고, 하나라도 걸리면 1.0 이다 (위 메모).
    """
    if docs is None:
        return 0.0
    calibrated = getattr(docs, "calibrated", False)
    queries = [query, message] + ([f"{message} {scope}"] if scope and not calibrated else [])
    best = 0.0
    for q in dict.fromkeys(queries):  # 같은 검색어는 한 번만
        top = docs.search(q, 1)
        if top:
            best = max(best, top[0].score)
    return best if calibrated or best == 0.0 else 1.0


def _scope_codes(extraction: Extraction, tables: RefTables) -> list[str]:
    """대화의 제품 코드 (제품, 제품군만 알면 그 제품군 제품들)."""
    if extraction.product_code in tables.products:
        return [extraction.product_code]
    family = extraction.product_family
    return [code for code, p in tables.products.items() if family and p.family == family]


def _product_facts(extraction: Extraction, tables: RefTables) -> list[str]:
    """기준표의 제품 정보 (가격은 넣지 않는다 — 견적은 결정 사항)."""
    lines = []
    for code in _scope_codes(extraction, tables)[:FAMILY_FACTS_MAX]:
        p = tables.products[code]
        facts = [
            (
                "Warranty",
                f"{p.warranty_months} months (start date: see POL-WARRANTY)"
                if p.warranty_months
                else "",
            ),
            (
                "Standard lead time",
                f"{p.std_lead_time_weeks} weeks (standard, not a confirmed delivery date)"
                if p.std_lead_time_weeks
                else "",
            ),
            ("Minimum order quantity", p.moq),
            ("Standards", p.standards.replace(";", ", ")),
            ("Certifications", p.certifications.replace(";", ", ")),
        ]
        body = "\n".join(f"- {name}: {value}" for name, value in facts if value)
        lines.append(f"[Product data · {code}] {p.name}\n{body}")
    return lines


def _intent_signals(
    chat: ChatIn, customer: list[str], advice: list[str], category, llm: LLMRouter
) -> tuple[bool, int]:
    """(지금 고객 말의 의도, 원격 조치 재발 횟수). 위 구현 메모 참고."""
    last_advice = advice[-1] if advice else None
    current = _intent(llm, last_advice, chat.message)
    attempts = 1 if current == RECURRENCE and last_advice else 0
    if category is not None and BUNDLE_OF.get(category) == Bundle.DIAGNOSIS:
        # 첫 고객 말은 조치를 받기 전이라 재발일 수 없다
        for i in range(max(1, len(customer) - INTENT_HISTORY), len(customer)):
            if i - 1 < len(advice) and _intent(llm, advice[i - 1], customer[i]) == RECURRENCE:
                attempts += 1
    return current, attempts


def _intent(llm: LLMRouter, advice: str | None, message: str) -> str:
    prompt = INTENT_PROMPT.format(advice=advice or "(none)", message=message)
    try:
        judgement = llm.judge("chat_intent", prompt, INTENT_OPTIONS)
    except Exception as e:  # 판단이 안 되면 아무 일도 없었던 것으로 본다
        _LOGGER.warning("챗봇 대화 의도 판단 실패: %s", e)
        return OTHER
    return OTHER if judgement.model == "fake" else judgement.answer


def _decision_requested(llm: LLMRouter, message: str) -> bool:
    """결정 유형 말이 실제로 결정을 요구하는지. 판단이 안 되면 요구한다고 본다 (넘기는 쪽)."""
    try:
        judgement = llm.judge(
            "chat_decision", DECISION_PROMPT.format(message=message), [DECISION, INFO]
        )
    except Exception as e:
        _LOGGER.warning("챗봇 결정 필요 판단 실패: %s", e)
        return True
    return judgement.model == "fake" or judgement.answer != INFO


def _about_our_products(llm: LLMRouter, message: str, tables: RefTables) -> bool | None:
    """제품 이름을 잘못 쓴 말도 우리 제품 이야기인지. 판단이 안 되면 None (전처럼 넘긴다)."""
    products = "\n".join(
        f"- {family}: " + ", ".join(names) for family, names in _families(tables).items()
    )
    try:
        judgement = llm.judge(
            "chat_our_product",
            OUR_PRODUCT_PROMPT.format(products=products, message=message),
            [YES, NO],
        )
    except Exception as e:
        _LOGGER.warning("챗봇 우리 제품 판단 실패: %s", e)
        return None
    return None if judgement.model == "fake" else judgement.answer == YES


def _decline_answer(language: str) -> str:
    """우리 제품 이야기가 아닌 말에 대한 고정 안내 (고객 언어, 모르는 언어는 영어)."""
    code = language.lower().replace("_", "-").split("-", 1)[0]
    return DECLINE_ANSWER.get(code, DECLINE_ANSWER["en"])


_MD_HEADING = re.compile(r"^[ \t]*#{1,6}[ \t]+", re.M)
_MD_BULLET = re.compile(r"^([ \t]*)[*•][ \t]+", re.M)
# 닫는 * 뒤에는 조사가 바로 붙는다 ("*부하*를")
_MD_EMPHASIS = re.compile(r"(?<![\w*])\*(?=\S)([^*\n]+?)(?<=\S)\*(?!\*)")


def _chat_text(text: str) -> str:
    """채팅 창 글: 굵게(**) · 목록(- , 1.) · [문서 · 절] 만 남긴다 (화면이 그것만 그린다)."""
    text = _MD_HEADING.sub("", text)
    text = _MD_BULLET.sub(r"\1- ", text)  # * · • 목록은 - 로
    text = _MD_EMPHASIS.sub(r"\1", text)
    text = text.replace("`", "")
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _partial_answer(prompt: str, reason: str, llm: LLMRouter) -> str | None:
    """결정 유형 전환: 답할 수 있는 부분 + 문의서로 넘긴다는 한 줄. 못 쓰면 None."""
    if not llm.enabled:
        return None
    try:
        return _chat_text(llm.write("chat_partial", prompt + PARTIAL_PROMPT.format(reason=reason)))
    except Exception as e:  # RateLimited 포함 — 전환 안내로 대신한다
        _LOGGER.warning("결정 유형 부분 답변 실패: %s", type(e).__name__)
        return None


def _handoff_answer(reason: str, language: str, llm: LLMRouter) -> str:
    """전환 안내를 고객 언어로. 확인되지 않으면 다시 옮기고, 끝내 안 되면 고정 문장."""
    text = reason + HANDOFF_SUFFIX
    code = language.lower().replace("_", "-").split("-", 1)[0]
    if code == "en":
        return text
    fallback = HANDOFF_FALLBACK.get(code, HANDOFF_FALLBACK["en"])  # 모르는 언어는 영어
    if not llm.enabled:
        return fallback
    prompt = TRANSLATE_PROMPT.format(language=language_name(code), text=text)
    for attempt in range(1, HANDOFF_TRANSLATE_ATTEMPTS + 1):
        try:
            out = llm.write("chat_handoff", prompt).strip()
        except RateLimited:
            break  # 기다려도 이번 응답 안에는 안 된다
        except Exception as e:
            _LOGGER.warning("전환 안내 번역 실패 (%d회): %s", attempt, type(e).__name__)
            continue
        if in_language(out, code):
            return out
        _LOGGER.warning("전환 안내가 %s 로 확인되지 않음 (%d회)", code, attempt)
        llm.invalidate_write("chat_handoff", prompt)  # 같은 결과가 캐시에서 다시 나오지 않게
    return fallback


def _ask_fields(
    extraction: Extraction, category, product_known: bool, tables: RefTables
) -> list[str]:
    """아직 안 나온 필수 항목 중 처리를 막는 것부터 1~2개."""
    if category is None:
        return []
    required, blocking = required_info(extraction.product_family, category, tables)
    have = set(extraction.provided_info) | set(extraction.field_values)
    for name, value in (
        (UNKNOWN_PRODUCT_FIELD, product_known),
        ("error_code", extraction.error_code),
        ("serial_no", extraction.serial_no),
        ("current_fw", extraction.fw_version),
    ):
        if value:
            have.add(name)
    missing = [f for f in required if f not in have]
    missing.sort(key=lambda f: f not in blocking)  # 정렬은 안정적이라 나머지 순서는 그대로
    return missing[:ASK_FIELDS_MAX]


def _evidence_block(
    evidence: list[Evidence], facts: list[str] | None = None, policy: list[Evidence] | None = None
) -> str:
    seen = {(e.doc_id, e.section) for e in evidence}
    extra = [e for e in policy or [] if (e.doc_id, e.section) not in seen]
    blocks = [
        *(facts or []),
        *(
            f"[{e.doc_id}{' · ' + e.section if e.section else ''}]\n{e.text[:EVIDENCE_CHARS]}"
            for e in [*evidence, *extra]
        ),
    ]
    return "\n\n".join(blocks) if blocks else "(none)"


def _conversation(history: list[str]) -> str:
    return "\n".join(
        f"{'Customer' if i % 2 == 0 else 'Assistant'}: {m.strip()}" for i, m in enumerate(history)
    )
