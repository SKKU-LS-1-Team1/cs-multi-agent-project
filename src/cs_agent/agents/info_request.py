# 추가정보 요청 에이전트 — ⑦ (CSA-27 · 담당 김동규 · Sprint 1)
#
# 그래프의 info_request 노드가 부른다. 두 경우에 불린다.
# - 규칙 처리(⑤) 결과 차단성 필수정보가 빠졌을 때 (route = info_request)
# - 상담원이 관리자 화면에서 "추가정보 요청문 작성" 버튼을 눌렀을 때 (ReviewAction.INFO_REQUEST,
#   상담원이 체크한 항목이 review.info_items 로 들어온다)
#
# 할 일
# 1. 빠진 항목(missing)만, 한 번에 모두 묻는 요청문을 고객 언어(language)로 쓴다. 여러 번 주고받지
#      않게.
# 2. 항목 이름(serial_no, incoterms …)을 고객이 알아듣는 말로 바꾸는 표를 만든다
#    (예: serial_no → "명판 사진의 시리얼 번호"). 항목 목록은 data/ref/required_info.csv 에 있다.
# 3. 문장은 Gemini로 쓴다: llm.write("info_request", prompt). 프롬프트에 문의 요약과 항목 목록을
#      넣는다.
# 4. 고객에게 직접 보내지 않는다 (P-01). 상담원 화면에 초안으로 올라가고, 승인 시 발송 → 상태
#    WAITING_CUSTOMER(SLA 시계 정지). 이 흐름은 graph/builder.py 가 처리한다.
#
# 완료 기준
# - valid 중 missing_info 가 있는 건: 요청문에 빠진 항목이 전부 들어감
# - 15개 언어 중 tickets 비중 상위 언어로 문장 확인 (en 56% 외)
#
# 참고: 기획서 v10 4.2, 관리자_대시보드_AI기능_구조검토.md 3장
#
# 정해 둔 것
# - 항목 라벨 표는 data/ref/info_field_codebook.csv (rules/tables.py field_labels, 영어 라벨)를
#   쓴다. LLM 이 고객 언어로 옮긴다. 표에 없는 항목은 이름을 풀어 쓴다(serial_no → "serial no").
#   빠진 항목이 겹치면 한 번만, 하나도 없으면 "문의 내용을 더 자세히" 한 항목으로 묻는다.
# - 빠짐 없이 묻기: 프롬프트에서 항목을 번호 목록으로 그 순서대로 쓰게 하고, 받은 글의 번호 목록
#   개수가 항목 수와 같은지 본다. 고객 언어가 아니면(agents/verification.detect_mismatch) 실패.
#   실패하면 사유를 붙여 한 번 더 쓰고, 그래도 안 되면 영어 틀 문장(template_request)으로 낸다.
# - LLM 이 꺼져 있거나(LLM_PROVIDER≠live) 호출이 실패해도 영어 틀 문장을 낸다
#   (상담원이 고쳐 보낸다).
# - 보낼 때 고객 언어로 (localize_request): 상담원이 승인한 요청문이 고객 언어가 아니면(영어 틀
#   문장, 상담원이 영어로 고친 글) 발송 직전에 고객 언어로 옮긴다 (graph/builder.py finish).
#   번역도 번호 목록 개수·언어를 같은 방식으로 보고 한 번 더 시도, 안 되면 승인한 글 그대로
#   보낸다. 상담원은 승인한 원문(info_request·review.edited_text)을 보고, 고객은 번역본
#   (final_reply)을 받는다. 번역본은 사람이 다시 보지 않는다 — 항목 수·언어 점검이 그 대신이다.
# - 프롬프트: 답을 하거나 약속하지 않는다, 목록 밖 질문 금지, 받는 사람·서명 이름은 지어내지 않는다.
#   문의 원문은 앞 2,000자만 넣는다.
import logging
import re
from collections.abc import Mapping, Sequence

from cs_agent.llm.router import LLMRouter

_LOGGER = logging.getLogger(__name__)

MAX_SUMMARY_CHARS = 2000
MAX_ATTEMPTS = 2
FALLBACK_ITEM = "More details about your request (product, symptom or documents needed)"

LANGUAGE_NAMES = {
    "en": "English",
    "es": "Spanish",
    "fr": "French",
    "th": "Thai",
    "it": "Italian",
    "id": "Indonesian",
    "zh": "Chinese (Simplified)",
    "tr": "Turkish",
    "ar": "Arabic",
    "ru": "Russian",
    "vi": "Vietnamese",
    "pt": "Portuguese",
    "de": "German",
    "ja": "Japanese",
    "pl": "Polish",
    "ko": "Korean",
}

# "1. " "2) " "**3.** " 와 전각·중국식 "１．" "1、" (뒤 공백 없어도 됨)
_NUMBERED = re.compile(r"^\s*(?:\*\*)?\d{1,2}(?:[.)](?:\*\*)?\s+|[．、）](?:\*\*)?\s*)\S", re.M)


def _field_labels() -> Mapping[str, str]:
    from cs_agent.rules.tables import load_tables

    return load_tables().field_labels


def item_labels(missing: Sequence[str], labels: Mapping[str, str]) -> list[str]:
    """빠진 항목 이름 → 고객에게 보일 라벨 (겹친 항목은 한 번, 순서 유지)."""
    seen: set[str] = set()
    out = []
    for field in missing:
        field = (field or "").strip()
        if not field or field in seen:
            continue
        seen.add(field)
        out.append(labels.get(field) or field.replace("_", " "))
    return out or [FALLBACK_ITEM]


def language_name(language: str | None) -> str:
    code = (language or "en").lower().split("-")[0]
    return LANGUAGE_NAMES.get(code, code)


def build_prompt(items: Sequence[str], language: str, summary: str) -> str:
    numbered = "\n".join(f"{i}. {item}" for i, item in enumerate(items, start=1))
    return (
        "You are a customer service agent at an electrical equipment manufacturer.\n"
        f"Write ONE short, polite message in {language_name(language)} asking the customer to "
        "send ALL of the items below in a single reply, so we can continue with their inquiry.\n"
        "Rules:\n"
        f"- List the items as a numbered list 1. to {len(items)}., one item per line, in this "
        "order. Translate each item naturally; keep product codes and abbreviations as written.\n"
        "- Do not answer the inquiry, promise anything, or ask for anything not in the list.\n"
        "- No subject line. Do not invent names for the customer or the sender; sign off as the "
        "customer service team.\n\n"
        f"Items:\n{numbered}\n\n"
        f"Customer inquiry (for context only):\n{summary[:MAX_SUMMARY_CHARS]}"
    )


def count_items(text: str) -> int:
    """글 안의 번호 목록 줄 수 ("1." "2)" "**3.**" …)."""
    return len(_NUMBERED.findall(text))


def check_request(text: str, items: Sequence[str], language: str) -> list[str]:
    """요청문이 항목을 빠짐 없이 고객 언어로 물었나. 문제 목록 (비면 통과)."""
    from cs_agent.agents.verification import detect_mismatch

    problems = []
    if not text.strip():
        return ["empty message"]
    found = count_items(text)
    if found != len(items):
        problems.append(f"the numbered list has {found} items but must have exactly {len(items)}")
    other = detect_mismatch(text, language, source_text="\n".join(items))
    if other:
        problems.append(f"it is written in '{other}', not {language_name(language)}")
    return problems


def template_request(items: Sequence[str]) -> str:
    """LLM 없이 쓰는 영어 틀 문장. 상담원이 고객 언어로 고쳐 보낸다."""
    numbered = "\n".join(f"{i}. {item}" for i, item in enumerate(items, start=1))
    return (
        "Dear customer,\n\n"
        "Thank you for contacting us. To review your inquiry, please send us the following "
        "information in one reply:\n\n"
        f"{numbered}\n\n"
        "Once we receive it, we will continue with your request.\n\n"
        "Best regards,\nCustomer Service Team"
    )


def write_info_request(missing: list[str], language: str, summary: str, llm: LLMRouter) -> str:
    """빠진 항목 → 고객 언어 요청문 초안."""
    items = item_labels(missing, _field_labels())
    if not llm.enabled:
        return template_request(items)
    prompt = build_prompt(items, language, summary)
    problems: list[str] = []
    for _ in range(MAX_ATTEMPTS):
        attempt = prompt
        if problems:
            attempt += "\n\nYour last message was rejected because " + "; ".join(problems) + "."
        try:
            text = llm.write("info_request", attempt).strip()
        except Exception:
            _LOGGER.exception("추가정보 요청문 작성 실패 → 영어 틀 문장")
            return template_request(items)
        problems = check_request(text, items, language)
        if not problems:
            return text
        _LOGGER.warning("추가정보 요청문 점검 실패: %s", problems)
    return template_request(items)


def translate_prompt(text: str, language: str, n_items: int) -> str:
    return (
        f"Translate the customer service message below into {language_name(language)}.\n"
        "Rules:\n"
        f"- Keep the numbered list with exactly {n_items} items, in the same order.\n"
        "- Keep product codes, model numbers, abbreviations and numbers exactly as written.\n"
        "- Do not add, remove or change any request. Output only the translated message.\n\n"
        f"Message:\n{text}"
    )


def localize_request(text: str, language: str, llm: LLMRouter) -> str:
    """보낼 요청문이 고객 언어가 아니면 고객 언어로 옮긴다. 이미 그 언어거나 실패하면 그대로."""
    from cs_agent.agents.verification import detect_mismatch

    if not text or not text.strip() or not llm.enabled:
        return text
    if detect_mismatch(text, language) is None:
        return text  # 이미 고객 언어 (또는 판단할 글이 없다)
    n_items = count_items(text)
    prompt = translate_prompt(text, language, n_items)
    problems: list[str] = []
    for _ in range(MAX_ATTEMPTS):
        attempt = prompt
        if problems:
            attempt += "\n\nYour last translation was rejected because " + "; ".join(problems) + "."
        try:
            translated = llm.write("translate_info_request", attempt).strip()
        except Exception:
            _LOGGER.exception("추가정보 요청문 번역 실패 → 승인한 글 그대로 보낸다")
            return text
        problems = []
        if not translated:
            problems.append("the translation was empty")
        elif count_items(translated) != n_items:
            problems.append(
                f"the numbered list has {count_items(translated)} items but must have {n_items}"
            )
        # 원문을 source_text 로 넘기면 번역 안 된 글이 '옮긴 구절'로 빠져 통과한다 → 넘기지 않는다
        other = translated and detect_mismatch(translated, language)
        if other:
            problems.append(f"it is written in '{other}', not {language_name(language)}")
        if not problems:
            return translated
        _LOGGER.warning("추가정보 요청문 번역 점검 실패: %s", problems)
    return text
