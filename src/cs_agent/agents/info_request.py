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
# - 항목 라벨 표(할 일 2)는 data/ref/info_request_labels.csv (rules/tables.py request_labels):
#   고객이 알아듣는 쉬운 영어 + 어디서 찾는지 (serial_no → "Serial number printed on the
#   product's nameplate label"). LLM 이 고객 언어로 옮긴다. 이 표에 없으면 info_field_codebook.csv
#   라벨(field_labels), 거기도 없으면 이름을 풀어 쓴다(serial_no → "serial no").
#   codebook 라벨은 고객 문의서·분석(CSA-26)이 쓰는 형식이라 바꾸지 않는다.
#   빠진 항목이 겹치면 한 번만, 하나도 없으면 "문의 내용을 더 자세히" 한 항목으로 묻는다.
# - 빠짐 없이 묻기: 프롬프트에서 항목을 번호 목록으로 그 순서대로 쓰게 하고, 받은 글의 번호 목록
#   개수가 항목 수와 같은지 본다. 고객 언어가 아니면(agents/verification.detect_mismatch) 실패.
#   실패하면 사유를 붙여 다시 쓴다 (최대 ATTEMPTS=3번, 호출 오류도 1번으로 센다). 3번 다 안 되거나
#   LLM 이 꺼져 있으면(LLM_PROVIDER≠live) 초안만 영어 틀 문장(template_request)으로 둔다 —
#   상담원 화면용이고, 고객에게는 아래 번역을 거쳐야만 나간다.
# - 보낼 때 고객 언어로 (localize_request): 상담원이 승인한 요청문이 고객 언어가 아니면(영어 틀
#   문장, 상담원이 영어로 고친 글) 발송 직전에 고객 언어로 옮긴다 (graph/builder.py finish).
#   번역도 번호 목록 개수·언어를 보고 최대 3번 시도한다. 그래도 안 되거나 LLM 이 꺼져 있으면
#   LocalizationError → 보내지 않고 보류(ON_HOLD, translation_error)해 상담원이 다시 승인한다.
#   **고객 언어가 아닌 글이 그대로 발송되는 경우는 없다.**
#   "이미 고객 언어"·"번역 통과"는 그 언어로 확인될 때만이다 (in_language): 다른 언어 신호가 없고,
#   ID·숫자를 뺀 글자가 MIN_CONFIRM_LETTERS 이상이고, 라틴 문자 언어는 lingua 가 그 언어로 고른다.
#   짧아서 판단이 안 되는 글("OK", "Hi, send model pls")은 확인 안 된 것으로 보고 번역·보류한다.
#   상담원은 승인한 원문(approved_reply)을 보고, 고객은 번역본(final_reply)을 받는다.
# - 점검에서 거른 응답은 LLM 캐시(CSA-45)에서 지운다 (llm.invalidate_write). 안 지우면 다시 승인해도
#   같은 프롬프트의 나쁜 응답을 캐시에서 그대로 받아 재시도가 의미 없다.
# - 프롬프트: 답을 하거나 약속하지 않는다, 목록 밖 질문 금지, 받는 사람·서명 이름은 지어내지 않는다.
#   문의 원문은 앞 2,000자만 넣는다.
import logging
import re
from collections.abc import Callable, Mapping, Sequence

from cs_agent.llm.router import LLMRouter

_LOGGER = logging.getLogger(__name__)

MAX_SUMMARY_CHARS = 2000
ATTEMPTS = 3  # 요청문 작성·번역 각각 최대 시도 횟수
MIN_CONFIRM_LETTERS = 20  # 고객 언어로 확인하려면 ID·숫자를 뺀 글자가 이만큼은 있어야 한다
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

    tables = load_tables()
    return {**tables.field_labels, **tables.request_labels}


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


class LocalizationError(RuntimeError):
    """요청문을 고객 언어로 옮기지 못했다 → 보내지 않고 보류한다 (영어로 보내지 않는다)."""


def _attempts(
    llm: LLMRouter, task: str, prompt: str, check: Callable[[str], list[str]], what: str
) -> tuple[str | None, list[str]]:
    """ATTEMPTS 번까지 쓰고 점검한다. 통과한 글, 아니면 (None, 마지막 문제)."""
    problems: list[str] = []
    for attempt in range(1, ATTEMPTS + 1):
        current = prompt
        if problems:
            current += "\n\nYour last attempt was rejected because " + "; ".join(problems) + "."
        try:
            text = llm.write(task, current).strip()
        except Exception as e:
            problems = [f"the call failed ({type(e).__name__})"]
            _LOGGER.warning("%s %d/%d번째 호출 실패: %s", what, attempt, ATTEMPTS, e)
            continue
        problems = check(text)
        if not problems:
            return text, []
        llm.invalidate_write(task, current)  # 거른 응답을 캐시에서 다시 받지 않게
        _LOGGER.warning("%s %d/%d번째 점검 실패: %s", what, attempt, ATTEMPTS, problems)
    return None, problems


def write_info_request(missing: list[str], language: str, summary: str, llm: LLMRouter) -> str:
    """빠진 항목 → 고객 언어 요청문 초안. 3번 다 실패하면 영어 틀 문장 (보낼 때 번역된다)."""
    items = item_labels(missing, _field_labels())
    if not llm.enabled:
        return template_request(items)
    text, _ = _attempts(
        llm,
        "info_request",
        build_prompt(items, language, summary),
        lambda t: check_request(t, items, language),
        "추가정보 요청문 작성",
    )
    return text if text is not None else template_request(items)


def translate_prompt(text: str, language: str, n_items: int) -> str:
    return (
        f"Translate the customer service message below into {language_name(language)}.\n"
        "Rules:\n"
        f"- Keep the numbered list with exactly {n_items} items, in the same order.\n"
        "- Keep product codes, model numbers, abbreviations and numbers exactly as written.\n"
        "- Do not add, remove or change any request. Output only the translated message.\n\n"
        f"Message:\n{text}"
    )


def in_language(text: str, language: str) -> bool:
    """글이 고객 언어로 **확인되는가**. 판단할 수 없으면 False (보내도 되는지 모르는 글이다).

    원문을 source_text 로 넘기지 않는다: 넘기면 번역 안 된 글이 '옮긴 구절'로 빠져 통과한다.
    """
    from cs_agent.agents.verification import (
        _SCRIPT_OF,
        LANGUAGE_CODES,
        _detector,
        detect_mismatch,
        strip_copied,
    )

    code = (language or "").lower().replace("_", "-").split("-")[0]
    if code not in LANGUAGE_CODES or detect_mismatch(text, code) is not None:
        return False
    rest = strip_copied(text, "")  # ID·숫자를 뺀 글
    if sum(ch.isalpha() for ch in rest) < MIN_CONFIRM_LETTERS:
        return False
    if code in _SCRIPT_OF:  # 비라틴 문자: detect_mismatch 가 그 문자가 절반 넘는 것을 봤다
        return True
    detected = _detector().detect_language_of(rest)
    return detected is not None and detected.iso_code_639_1.name.lower() == code


def check_translation(translated: str, language: str, n_items: int) -> list[str]:
    """번역본 점검: 번호 목록 개수가 그대로인가, 고객 언어로 확인되는가."""
    from cs_agent.agents.verification import detect_mismatch

    if not translated.strip():
        return ["the translation was empty"]
    problems = []
    found = count_items(translated)
    if found != n_items:
        problems.append(f"the numbered list has {found} items but must have {n_items}")
    if not in_language(translated, language):
        other = detect_mismatch(translated, language)
        problems.append(
            f"it is written in '{other}', not {language_name(language)}"
            if other
            else f"it could not be confirmed as {language_name(language)}"
        )
    return problems


def localize_request(text: str, language: str, llm: LLMRouter) -> str:
    """보낼 요청문을 고객 언어로. 그 언어로 확인되면 그대로, 3번 다 실패하면 LocalizationError."""
    if not text or not text.strip():
        raise LocalizationError("보낼 요청문이 비어 있다")
    if in_language(text, language):
        return text  # 이미 고객 언어로 확인됨
    if not llm.enabled:
        raise LocalizationError(
            f"{language_name(language)} 로 옮길 번역 모델이 꺼져 있다 (LLM_PROVIDER≠live)"
        )
    n_items = count_items(text)
    translated, problems = _attempts(
        llm,
        "translate_info_request",
        translate_prompt(text, language, n_items),
        lambda t: check_translation(t, language, n_items),
        "추가정보 요청문 번역",
    )
    if translated is None:
        raise LocalizationError(
            f"{language_name(language)} 번역 {ATTEMPTS}번 실패 — 보내지 않고 보류: "
            + "; ".join(problems)
        )
    return translated
