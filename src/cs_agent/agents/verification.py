# 자동 점검(검증) 에이전트 — ⑩ (CSA-31 · 담당 김동규 · Sprint 2)
#
# 그래프의 verify 노드가 부른다. 실패하면 실패 사유를 답변 작성(⑨)에 넘겨 재작성하고,
# 최대 2회(settings.max_verify_retries, S-06) 넘으면 보류(ON_HOLD, P-03)로 상담원 화면에 올린다.
# 재시도·보류 분기는 graph/builder.py 가 이미 처리한다. 여기서는 점검 결과 목록만 돌려준다.
#
# 할 일 — 코드 점검 1~5를 먼저 하고, 모두 통과했을 때만 6(LLM)을 부른다 (호출 수·속도 절약)
# 1. slots: 틀의 필수 슬롯이 다 찼는가 (drafting.TEMPLATES[category].required_slots)
# 2. values: 답변 속 수치·문서 ID가 슬롯(조회값)과 같은가 (정규식으로 값 뽑아 비교)
# 3. specs: 고객이 말하지 않았고 근거에도 없는 사양(kV, kA, kW, IEC/UL …)을 넣었는가 (C-05).
#    비교할 때 공백 차이("1000 kVA" vs "1000kVA")는 무시한다.
# 4. language: 초안 언어 = 전달받은 검토 언어(en). 고객 언어 번역은 상담원 승인 후 수행한다.
# 5. banned: 진단형이 원인을 단정했나 / 정책형이 승인·반려를 썼나 (금지 표현 목록)
# 6. grounding: 모든 문장이 근거에서 나왔는가 — llm.judge("verify_grounding", …, ["yes","no"])
#    근거 없는 문장 번호를 받아 reason 에 넣으면 재작성 때 그대로 쓴다.
#
# 각 점검은 CheckResult(name, passed, reason)로 돌려준다. reason 은 사람이 읽는 실패 사유
# ("견적 유효기간 누락", "2번 문장 근거 없음")로 쓴다. 관리자 화면(CSA-42)에 그대로 표시된다.
#
# 완료 기준
# - 일부러 틀린 값·근거 없는 문장을 넣은 답변을 잡아낸다 (사례 10개 이상으로 확인)
# - valid에서 점검 통과율·재작성 횟수 분포 보고
#
# 참고: 에이전트_구조_제안.md 4장
#
# 정해 둔 것
# - "근거"(sources) = 문의 원문 + 확정 근거(evidence: 본문·doc_id·절·메타데이터) + 슬롯 값 +
#   draft.cited + 기준표(CSA-19)의 해당 제품 행(제품명·사양값·펌웨어 이력·보증·납기·정가 …).
#   해당 제품 = 문의·근거·슬롯에 제품 코드나 제품명이 나온 제품. 기준표 값은 코드가 조회한
#   사실이라 근거로 친다. 다른 제품의 값은 근거가 아니다.
# - 값 비교: 숫자는 쉼표·마침표 표기 차이("2,515.00" / "2.515,00", "1,5")를 모두 해석해 보고
#   하나라도 맞으면 같다. 단위는 SI 접두어를 풀어 비교한다("25.8 kV" = "25800 V").
#   목록·범위("15, 20, 30 A", "380–480 V")는 마지막 단위를 앞 숫자에도 붙인다.
# - 2 values (값 지어내기): 답변의 문서·제품·RMA ID, 에러코드, 금액, 기간(주·개월·일 …), 날짜,
#   버전 같은 소수, 100 이상의 숫자가 근거에 없으면 실패. 필수 슬롯의 숫자는 답변에 그대로
#   나와야 한다 (LLM 이 조회값을 바꿔 쓰지 않았는지).
# - 3 specs (C-05): 물리·전기 단위가 붙은 값, 규격(IEC/EN/UL/IEEE/ISO …), 인증 마크(CE, UL, KC …)가
#   근거에 없으면 실패. 규격은 근거보다 덜 구체적으로 쓴 것("IEC 60947")은 통과, 더 구체적이거나
#   다른 부(-4-1 등)면 실패.
# - 4 language: 근거·문의에서 그대로 옮긴 구절(영어 속성명·제품명)과 ID·숫자를 빼고 감지한다.
#   비라틴 문자 언어(th·ar·ru·zh·ja·ko)는 문자 종류로, 라틴 문자 언어는 lingua 로 본다.
#   짧은 글은 언어별 기능어 수로 한 번 더 본다. tickets 실제 회신 3,635건 기준 오탐 1건(0.03%),
#   다른 언어 회신 탐지 99.4% (tests/test_verification.py).
# - 5 banned: 이 문의에 대한 판정만 잡는다. 문장에 추정 표현("may", "possible", "가능성")이 있으면
#   원인 단정이 아니고, 조건 표현("if", "once", "승인되면")이 있으면 승인·반려 판정이 아니다.
#   정책 조항 인용("After 30 days: not accepted")은 판정이 아니라 통과.
# - 6 grounding: 답변 전체를 한 번 묻고(yes 면 1회로 끝), no 거나 확신도가 낮으면 문장마다 다시
#   물어 근거 없는 문장 번호를 찾는다(병렬). 인사·감사·추가 자료 요청·"문서에 없다"는 문장은
#   근거가 필요 없는 문장으로 본다. 판단 모델이 꺼져 있으면(LLM_PROVIDER≠live) 생략하고 통과.
#   호출이 실패하면 실패로 남겨 상담원이 보게 한다 (근거 확인 없이 통과시키지 않는다).
# - 앞 점검이 실패하면 6 은 부르지 않고 결과 목록에서도 뺀다 (재작성 후 다시 본다).
# - LLM 이 꺼져 쓴 자리표시 답변(FakeWriter)은 내용 점검을 생략한다 (흐름 확인용).
import contextvars
import re
import unicodedata
from collections.abc import Iterable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from cs_agent.domain import BUNDLE_OF, Bundle, Category
from cs_agent.llm.clients import FakeJudge, FakeWriter
from cs_agent.llm.router import LLMRouter
from cs_agent.schemas import CheckResult, Draft, Evidence

GROUNDING_TASK = "verify_grounding"
GROUNDING_MIN_CONFIDENCE = 0.5  # 이보다 낮은 판단은 "불확실" (통과시키지 않는다)
GROUNDING_WORKERS = 4
REFERENCE_CHARS = 2500  # 근거 하나를 프롬프트에 넣는 최대 길이
SNIPPET_CHARS = 60  # reason 에 인용하는 문장 길이
MIN_CHECKED_INTEGER = 100  # 단위 없는 정수는 이 이상만 지어낸 값인지 본다


# 글 다루기 -----------------------------------------------------------------------------------


def _nfkc(text: str) -> str:
    return unicodedata.normalize("NFKC", text or "")


def _snippet(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= SNIPPET_CHARS else text[: SNIPPET_CHARS - 1] + "…"


_ABBREVIATIONS = ("e.g.", "i.e.", "approx.", "no.", "nr.", "fig.", "etc.", "vs.", "ca.", "z.b.")
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=\S)|(?<=[。！？])|\n+")


def split_sentences(text: str) -> list[str]:
    """답변 → 문장 목록 (번호는 1부터 reason 에 쓴다). 소수점·약어에서는 자르지 않는다."""
    pieces: list[str] = []
    for raw in _SENTENCE_END.split(_nfkc(text)):
        part = raw.strip(" \t-•*·")
        if not part:
            continue
        if pieces and pieces[-1].lower().endswith(_ABBREVIATIONS):
            pieces[-1] = f"{pieces[-1]} {part}"
        else:
            pieces.append(part)
    return pieces


def _script(ch: str) -> str:
    name = unicodedata.name(ch, "")
    for script in ("THAI", "ARABIC", "CYRILLIC", "HANGUL", "HIRAGANA", "KATAKANA", "LATIN"):
        if name.startswith(script):
            return script
    return "CJK" if "CJK" in name else "OTHER"


_LETTERS = re.compile(r"[^\W\d_]+")


def _words(text: str) -> list[str]:
    """글자 덩어리. 문자 종류가 바뀌는 곳에서 나눈다 ("kW的Anti" → kW, 的, Anti)."""
    out = []
    for match in _LETTERS.finditer(text):
        word = match.group()
        start = 0
        for i in range(1, len(word)):
            if _script(word[i]) != _script(word[i - 1]):
                out.append(word[start:i])
                start = i
        out.append(word[start:])
    return out


# 값 뽑기 ------------------------------------------------------------------------------------

# 문서·제품·RMA·티켓 ID: 대문자 2자 이상으로 시작하고 '-' 로 이어진 토큰
# (DS-ACB-AS-2000, RMA-260057, RS-485, AC-3, FAQ-LV_BREAKER). 에러코드: E.OC, T.LT
# '-' 뒤 조각은 대문자만이거나 숫자를 포함해야 한다 ("KC-Zertifikat" 같은 복합어는 ID 가 아니다)
_ID = re.compile(
    r"(?<![\w.])[A-Z][A-Z0-9]+(?:-(?:[A-Z0-9]+(?:_[A-Z0-9]+)*(?![a-z])|[A-Za-z.]*\d(?:[A-Za-z0-9.]*[A-Za-z0-9])?))+"
    r"(?![\w-])"
)
_ERROR_CODE = re.compile(r"(?<![\w.])[A-Z]{1,3}\.[A-Z][A-Z0-9]{0,4}(?![\w.])")
_STANDARD = re.compile(
    r"\b(IEC|EN|UL|IEEE|ISO|ANSI|NEMA|CSA\s?C22\.2|KS\s?C|JIS\s?C|GB/?T|DIN|BS|AS/NZS|IEC/EN)"
    r"\s?(?:No\.\s?)?(\d{2,6}(?:[-.:/]\d+)*(?:-\d+)*)"
)  # 대소문자 구분: 스페인어 "en 2025" 가 EN 규격으로 잡히지 않게
_MARKS = (
    "CE", "UL", "cUL", "cULus", "CB", "KC", "CCC", "TÜV", "DNV", "ATEX", "IECEx", "RoHS",
    "REACH", "UKCA", "EAC", "KEMA", "SEMKO", "BIS", "PSE", "RCM", "NOM", "CSA",
)  # fmt: skip
_MARK = re.compile(r"(?<![\w-])(" + "|".join(re.escape(m) for m in _MARKS) + r")(?![\w-])")
_DATE = re.compile(
    r"(?<!\d)(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})(?!\d)"  # 2025-11-22
    r"|(?<!\d)(\d{4})\s?[年년]\s?(\d{1,2})\s?[月월]\s?(\d{1,2})\s?[日일]?"  # 2025年11月22日
    r"|(?<![\d.])(\d{1,2})[./](\d{1,2})[./](\d{4})(?!\d)"  # 22.11.2025, 22/11/2025
)
# 공백 천 단위 구분("2 500 m", "1 000,50") 을 먼저 맞춘다 (pl·fr·ru 등)
_NUM = r"\d{1,3}(?:[ \u202f\u00a0]\d{3})+(?:[.,]\d+)?(?!\d)|\d+(?:[.,\u202f\u00a0']\d+)*"
_NUMBER = re.compile(rf"(?<![\w.,])(?:{_NUM})")
_VERSION = re.compile(r"(?<![\w.])[vV](\d+(?:\.\d+)+)(?!\w|\.\d)")  # v3.20
_LIST_SEP = r"\s*(?:,|/|-|–|—|~|～|〜|to|and|or|à|a|bis|до|至|และ|e|y|i|и|ve|dan|và)\s*"

# 물리·전기 단위 → (기준 단위, 배수). 긴 것부터 맞춘다.
_SPEC_UNITS: dict[str, tuple[str, float]] = {
    "MVA": ("VA", 1e6), "kVA": ("VA", 1e3), "KVA": ("VA", 1e3), "VA": ("VA", 1),
    "Mvar": ("var", 1e6), "kvar": ("var", 1e3), "kVAr": ("var", 1e3), "kVAR": ("var", 1e3),
    "MWh": ("Wh", 1e6), "kWh": ("Wh", 1e3), "Wh": ("Wh", 1), "Ah": ("Ah", 1),
    "MW": ("W", 1e6), "kW": ("W", 1e3), "KW": ("W", 1e3), "W": ("W", 1),
    "kV": ("V", 1e3), "KV": ("V", 1e3), "mV": ("V", 1e-3), "VAC": ("V", 1), "VDC": ("V", 1),
    "Vac": ("V", 1), "Vdc": ("V", 1), "V": ("V", 1),
    "kA": ("A", 1e3), "KA": ("A", 1e3), "mA": ("A", 1e-3), "AF": ("AF", 1), "AT": ("AT", 1),
    "A": ("A", 1),
    "kHz": ("Hz", 1e3), "Hz": ("Hz", 1),
    "°C": ("°C", 1), "°F": ("°F", 1), "%": ("%", 1),
    "mm²": ("mm2", 1), "mm2": ("mm2", 1), "mm": ("m", 1e-3), "cm": ("m", 1e-2), "km": ("m", 1e3),
    "m": ("m", 1), "kg": ("kg", 1), "N·m": ("Nm", 1), "N.m": ("Nm", 1), "Nm": ("Nm", 1),
    "kN": ("N", 1e3), "MPa": ("Pa", 1e6), "kPa": ("Pa", 1e3), "Pa": ("Pa", 1),
    "mbar": ("bar", 1e-3), "bar": ("bar", 1),
    "MΩ": ("Ω", 1e6), "kΩ": ("Ω", 1e3), "Ω": ("Ω", 1), "ohm": ("Ω", 1),
    "ms": ("s", 1e-3), "μs": ("s", 1e-6), "s": ("s", 1), "sec": ("s", 1), "min": ("s", 60),
    "minute": ("s", 60), "minutes": ("s", 60),
    "Mbps": ("bps", 1e6), "kbps": ("bps", 1e3), "bps": ("bps", 1), "baud": ("bps", 1),
    "dBA": ("dB", 1), "dB": ("dB", 1), "lx": ("lx", 1),
}  # fmt: skip
# 기간 (납기·보증·출하 약속). 고객 언어로 쓰므로 언어별 단어를 같은 단위로 묶는다.
_DURATION_WORDS: dict[str, tuple[str, ...]] = {
    "week": (
        "weeks", "week", "wks", "wk", "semanas", "semana", "semaines", "semaine", "settimane",
        "settimana", "Wochen", "Woche", "tygodnie", "tygodni", "tydzień", "hafta", "minggu",
        "tuần", "недели", "недель", "неделя", "нед", "أسابيع", "أسبوع", "สัปดาห์", "週間", "周",
        "週", "주",
    ),
    "month": (
        "months", "month", "meses", "mes", "mois", "mesi", "mese", "Monaten", "Monate", "Monat",
        "miesięcy", "miesiące", "miesiąc", "ay", "aylık", "bulan", "tháng", "месяцев", "месяца",
        "месяц", "мес", "أشهر", "شهرًا", "شهرا", "شهر", "เดือน",
        "个月", "ヶ月", "か月", "カ月", "개월",
    ),
    "day": (
        "business days", "working days", "days", "day", "días", "día", "jours", "jour", "giorni",
        "giorno", "Tagen", "Tage", "Tag", "dni", "dzień", "gün", "hari", "ngày", "дней", "дня",
        "день", "أيام", "يوم", "วัน", "天", "日", "일",
    ),
    "year": (
        "years", "year", "años", "año", "ans", "années", "année", "anni", "anno", "Jahren",
        "Jahre", "Jahr", "lata", "lat", "rok", "yıl", "tahun", "năm", "лет", "года", "год",
        "سنوات", "سنة", "ปี", "年", "년",
    ),
    "hour": (
        "hours", "hour", "hrs", "horas", "hora", "heures", "heure", "ore", "ora", "Stunden",
        "Stunde", "godzin", "godziny", "saat", "jam", "giờ", "часов", "часа", "час", "ساعات",
        "ساعة", "ชั่วโมง", "小时", "時間", "시간",
    ),
}  # fmt: skip
_CURRENCY = r"USD|EUR|KRW|JPY|CNY|GBP|US\$|\$|€|₩|¥|£|달러|美元|ドル|円|원"


def _unit_regex(words: Iterable[str]) -> str:
    return "|".join(re.escape(w) for w in sorted(words, key=len, reverse=True))


_SPEC_Q = re.compile(rf"(?<![\w.,])({_NUM})\s?({_unit_regex(_SPEC_UNITS)})(?![^\W\d_])")
_IP = re.compile(r"\bIP\s?([0-9X]{2}[A-DHMSW]?)\b")
_DURATION_UNIT = {w: unit for unit, words in _DURATION_WORDS.items() for w in words}
_DURATION_Q = re.compile(
    rf"(?<![\w.,])({_NUM})\s?(?:-\s?)?({_unit_regex(_DURATION_UNIT)})(?![^\W\d_])", re.I
)
_MONEY = re.compile(
    rf"(?:({_CURRENCY})\s?({_NUM}))|(?:(?<![\w.,])({_NUM})\s?({_CURRENCY})(?![A-Za-z]))"
)


def number_values(token: str) -> frozenset[float]:
    """숫자 표기 → 가능한 값들. "1,000" 은 1000 또는 1.0, "2.515,00" 은 2515."""
    s = re.sub(r"[ \u202f\u00a0']", "", token)
    if not s:
        return frozenset()
    if "," in s and "." in s:
        decimal = "," if s.rfind(",") > s.rfind(".") else "."
        thousands = "." if decimal == "," else ","
        s = s.replace(thousands, "").replace(decimal, ".")
        return frozenset({_f(s)}) if _f(s) is not None else frozenset()
    for sep in (",", "."):
        if sep in s:
            parts = s.split(sep)
            values = set()
            if all(len(p) == 3 for p in parts[1:]):  # 천 단위 구분
                values.add(_f("".join(parts)))
            if len(parts) == 2:  # 소수
                values.add(_f(f"{parts[0]}.{parts[1]}"))
            return frozenset(v for v in values if v is not None)
    value = _f(s)
    return frozenset({value}) if value is not None else frozenset()


def _f(s: str) -> float | None:
    try:
        return round(float(s), 9)
    except ValueError:
        return None


def _scaled(values: Iterable[float], factor: float) -> set[float]:
    return {round(v * factor, 9) for v in values}


@dataclass(frozen=True)
class Value:
    """답변에서 뽑은 값 하나. kind 별로 근거와 비교한다."""

    kind: str  # spec | ip | standard | mark | id | duration | money | date | number
    text: str  # 사람이 읽는 원문 표기
    key: Any  # 비교 키


def _masked(text: str, spans: Iterable[tuple[int, int]]) -> str:
    chars = list(text)
    for start, end in spans:
        for i in range(start, end):
            chars[i] = " "
    return "".join(chars)


_LIST_WINDOW = 40  # 목록 앞 숫자 하나를 찾을 때 볼 앞 글자 수


@lru_cache(maxsize=8)
def _list_item(unit_pattern: str) -> re.Pattern[str]:
    return re.compile(rf"({_NUM})(\s?(?:{unit_pattern}))?{_LIST_SEP}$", re.I)


def _propagate(text: str, start: int, unit_pattern: str) -> list[tuple[str, int]]:
    """'15, 20, 30 A' 의 30 앞 숫자들 (단위를 같이 붙일 것).

    앞 숫자에 제 단위가 있으면 ("25 kA / 3 s") 거기서 멈춘다.
    """
    out = []
    pattern = _list_item(unit_pattern)
    end = start
    while True:
        window_start = max(0, end - _LIST_WINDOW)
        m = pattern.search(text, window_start, end)
        cut = (
            m
            and m.start() == window_start
            and window_start > 0
            and text[window_start - 1].isdigit()
        )
        if not m or cut or m.group(2):
            return out
        out.append((m.group(1), m.start(1)))
        end = m.start()


_LATEX_INLINE = re.compile(r"\$([^$\n]*\\[^$\n]*)\$")  # $5\,\text{N·m}$
_LATEX_COMMAND = re.compile(r"\\(?:text|mathrm)\{([^}]*)\}|\\[,;:! ]|\\[A-Za-z]+")


def _strip_latex(text: str) -> str:
    """LLM 이 쓴 인라인 수식의 $ 를 달러로 읽지 않게 수식 기호를 벗긴다."""
    return _LATEX_INLINE.sub(
        lambda m: " " + _LATEX_COMMAND.sub(lambda c: c.group(1) or " ", m.group(1)) + " ", text
    )


def extract_values(text: str) -> list[Value]:
    """글 → 비교할 값 목록.

    ID·규격·날짜를 먼저 뽑고 그 자리를 지워 숫자가 두 번 잡히지 않게 한다.
    """
    text = _strip_latex(_nfkc(text))
    values: list[Value] = []
    spans: list[tuple[int, int]] = []

    for m in _STANDARD.finditer(text):
        org = re.sub(r"\s", "", m.group(1)).upper()
        values.append(Value("standard", m.group(0), (org, m.group(2))))
        spans.append(m.span())
    for m in _ID.finditer(_masked(text, spans)):
        values.append(Value("id", m.group(0), m.group(0).upper()))
        spans.append(m.span())
    for m in _ERROR_CODE.finditer(_masked(text, spans)):
        values.append(Value("id", m.group(0), m.group(0).upper()))
        spans.append(m.span())
    for m in _IP.finditer(_masked(text, spans)):
        values.append(Value("ip", m.group(0), m.group(1).upper()))
        spans.append(m.span())
    for m in _DATE.finditer(_masked(text, spans)):
        g = m.groups()
        y, mo, d = (
            (g[0], g[1], g[2]) if g[0] else (g[3], g[4], g[5]) if g[3] else (g[8], g[7], g[6])
        )
        if 1 <= int(mo) <= 12 and 1 <= int(d) <= 31:
            values.append(Value("date", m.group(0), (int(y), int(mo), int(d))))
            spans.append(m.span())
    for m in _VERSION.finditer(_masked(text, spans)):
        values.append(Value("number", m.group(1), number_values(m.group(1))))
        spans.append(m.span())
    for m in _MARK.finditer(_masked(text, spans)):
        values.append(Value("mark", m.group(0), m.group(0).upper()))

    masked = _masked(text, spans)
    for m in _MONEY.finditer(masked):
        number = m.group(2) or m.group(3)
        currency = (m.group(1) or m.group(4)).replace("US$", "USD").replace("$", "USD")
        values.append(Value("money", m.group(0).strip(), (currency, number_values(number))))
        spans.append(m.span())
    masked = _masked(text, spans)
    for m in _DURATION_Q.finditer(masked):
        unit = _DURATION_UNIT.get(m.group(2)) or _DURATION_UNIT[_lower_key(m.group(2))]
        for number, _ in [(m.group(1), m.start(1))] + _propagate(
            masked, m.start(1), _unit_regex(_DURATION_UNIT)
        ):
            values.append(
                Value("duration", f"{number} {m.group(2)}", (unit, number_values(number)))
            )
        spans.append(m.span())
    masked = _masked(text, spans)
    unit_pattern = _unit_regex(_SPEC_UNITS)
    for m in _SPEC_Q.finditer(masked):
        base, factor = _SPEC_UNITS[m.group(2)]
        numbers = [(m.group(1), m.start(1))] + _propagate(masked, m.start(1), unit_pattern)
        for number, start in numbers:
            key = (base, frozenset(_scaled(number_values(number), factor)))
            values.append(Value("spec", f"{number} {m.group(2)}", key))
            spans.append((start, start + len(number)))
        spans.append(m.span())
    masked = _masked(text, spans)
    for m in _NUMBER.finditer(masked):
        token = m.group(0)
        if _is_list_marker(masked, m.start(), m.end()):
            continue
        nums = number_values(token)
        is_decimal = bool(re.search(r"[.,]\d", token)) and not re.fullmatch(
            r"\d{1,3}(,\d{3})+", token
        )
        if is_decimal or any(v >= MIN_CHECKED_INTEGER for v in nums):
            values.append(Value("number", token, nums))
    return values


def _lower_key(word: str) -> str:
    return next(k for k in _DURATION_UNIT if k.lower() == word.lower())


def _is_list_marker(text: str, start: int, end: int) -> bool:
    """줄 앞의 '1.' '2)' 같은 목록 번호."""
    line_start = text.rfind("\n", 0, start) + 1
    return not text[line_start:start].strip() and text[end : end + 1] in (".", ")")


# 근거 ---------------------------------------------------------------------------------------


@dataclass
class Sources:
    """답변 값과 비교할 근거 묶음."""

    text: str  # 모든 근거 글 (NFKC)
    values: list[Value] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.by_kind: dict[str, list[Value]] = {}
        for value in self.values:
            self.by_kind.setdefault(value.kind, []).append(value)
        self.all_numbers: set[float] = set()
        for value in self.values:
            if value.kind in ("number", "duration", "money"):
                self.all_numbers |= set(value.key if value.kind == "number" else value.key[1])
            elif value.kind == "spec":
                self.all_numbers |= set(value.key[1])
        for m in _NUMBER.finditer(self.text):  # 단위 없는 작은 수·목록 숫자까지
            self.all_numbers |= number_values(m.group(0))
        # 단위가 붙지 않은 숫자 (표 머리글에 단위가 있는 근거 "| Rated voltage (kV) | 25.8 |")
        self.bare_numbers: set[float] = set()
        for m in _NUMBER.finditer(_unitless(self.text)):
            self.bare_numbers |= number_values(m.group(0))
        self.keys = {kind: {v.key for v in vs} for kind, vs in self.by_kind.items()
                     if kind in ("id", "mark", "ip")}  # fmt: skip

    def supports(self, value: Value) -> bool:
        if value.kind in ("id", "mark", "ip"):
            # 경계를 지켜 뽑은 값끼리 비교한다 ("CE" 가 CERTIFICATE 안에서 맞으면 안 된다)
            return value.key in self.keys.get(value.kind, set())
        if value.kind == "standard":
            org, number = value.key
            return any(
                o == org
                and (n == number or n.startswith(number + "-") or n.startswith(number + "."))
                for o, n in (v.key for v in self.by_kind.get("standard", []))
            )
        if value.kind == "date":
            return any(v.key == value.key for v in self.by_kind.get("date", []))
        if value.kind == "spec":
            base, nums = value.key
            if any(
                b == base and nums & n for b, n in (v.key for v in self.by_kind.get("spec", []))
            ):
                return True
            # 표 머리글에 단위가 있는 경우: 근거에 단위 없이 같은 숫자가 있으면 통과
            number = re.match(_NUM, value.text)
            return bool(number) and bool(number_values(number.group(0)) & self.bare_numbers)
        if value.kind in ("duration", "money"):
            unit, nums = value.key
            same = [v for v in self.by_kind.get(value.kind, []) if v.key[0] == unit]
            return any(nums & v.key[1] for v in same)  # 단위까지 같아야 한다 (13주 ≠ 13개)
        if value.kind == "number":
            if value.key:
                return bool(value.key & self.all_numbers)
            # 1.2.3 처럼 수로 읽히지 않는 버전: 숫자 경계를 지켜 그대로 찾는다
            return bool(re.search(rf"(?<![\d.]){re.escape(value.text)}(?![\d])", self.text))
        return True


def _unitless(text: str) -> str:
    """단위가 붙은 값·ID·날짜·규격 자리를 지운 글 (남은 숫자는 단위 없는 숫자)."""
    for pattern in (_STANDARD, _ID, _IP, _DATE, _MONEY, _DURATION_Q, _SPEC_Q):
        text = pattern.sub(lambda m: " " * len(m.group(0)), text)
    return text


@lru_cache
def _product_master() -> dict[str, dict[str, str]]:
    import csv

    from cs_agent.config import get_settings

    path = get_settings().ref_dir / "product_master.csv"
    if not path.exists():
        return {}
    with path.open(encoding="utf-8-sig", newline="") as f:
        return {row["product_code"]: row for row in csv.DictReader(f)}


def _commercial_terms(row: dict[str, str]) -> str:
    """제품 마스터의 보증·납기·정가·최소 주문을 단위가 붙은 글로 (기간·금액은 단위까지 비교한다)."""
    terms = []
    if row.get("warranty_months"):
        terms.append(f"warranty {row['warranty_months']} months")
    if row.get("std_lead_time_weeks"):
        terms.append(f"lead time {row['std_lead_time_weeks']} weeks")
    if row.get("list_price_usd"):
        terms.append(f"list price USD {row['list_price_usd']}")
    if row.get("moq"):
        terms.append(f"MOQ {row['moq']} units")
    return "; ".join(terms)


def _reference_rows(texts: Sequence[str], codes: Iterable[str]) -> list[str]:
    """문의·근거·슬롯에 나온 제품의 기준표 행 (CSA-19). 표가 없으면 빈 목록."""
    try:
        from cs_agent.rules.tables import load_tables

        tables = load_tables()
    except Exception:  # 기준표가 없는 환경 (점검은 기준표 없이도 돈다)
        return []
    joined = "\n".join(texts)
    wanted = set(codes)
    for code, product in tables.products.items():
        if code in joined or (product.name and product.name in joined):
            wanted.add(code)
    rows: list[str] = []
    master = _product_master()
    for code in sorted(wanted):
        product = tables.products.get(code)
        if product:
            rows.append(f"{product.code} {product.name}")
        if code in master:
            rows.append(" | ".join(f"{k}: {v}" for k, v in master[code].items() if v))
            rows.append(_commercial_terms(master[code]))
        for fact in tables.spec_facts.get(code, []):
            rows.append(f"{fact.get('attribute', '')}: {fact.get('value', '')}")
        for fw in tables.firmware.get(code, []):
            rows.append(f"firmware {fw.get('fw_version', '')} {fw.get('release_date', '')}")
    return rows


def build_sources(inquiry_text: str, evidence: Sequence[Evidence], draft: Draft) -> Sources:
    texts = [inquiry_text]
    codes: set[str] = set()
    for e in evidence:
        texts += [e.text, e.doc_id, e.section or "", f"{e.doc_id}#{e.section or ''}"]
        texts += [str(v) for v in e.metadata.values() if v]
        if e.metadata.get("product_code"):
            codes.add(e.metadata["product_code"])
        if e.source == "docs" and "-" in e.doc_id:
            codes.add(e.doc_id.split("-", 1)[1])  # DS-ACB-AS-2000 → ACB-AS-2000
    texts += [f"{k}: {v}" for k, v in draft.slots.items()]
    # CSA-29 견적 슬롯은 수치만 담고 필드명으로 USD를 명시한다.
    # 통화를 원천 문맥에도 붙여야 코드가 계산한 합계를 근거 없는 금액으로 오인하지 않는다.
    texts += [
        f"{key}: {draft.slots[key]} USD"
        for key in ("unit_price_usd", "total_usd")
        if draft.slots.get(key)
    ]
    texts += list(draft.cited)
    texts += _reference_rows(texts, codes)
    text = _nfkc("\n".join(t for t in texts if t))
    return Sources(text, extract_values(text))


# 1 slots · 2 values · 3 specs -------------------------------------------------------------


def check_slots(draft: Draft, required_slots: Sequence[str]) -> CheckResult:
    missing = [s for s in required_slots if not str(draft.slots.get(s, "") or "").strip()]
    if missing:
        return CheckResult(
            name="slots", passed=False, reason="필수 슬롯 누락: " + ", ".join(missing)
        )
    return CheckResult(name="slots", passed=True)


_VALUE_KINDS = ("id", "duration", "money", "date", "number")
_SPEC_KINDS = ("spec", "ip", "standard", "mark")
_KIND_LABEL = {
    "id": "ID",
    "duration": "기간",
    "money": "금액",
    "date": "날짜",
    "number": "숫자",
    "spec": "사양",
    "ip": "보호 등급",
    "standard": "규격",
    "mark": "인증",
}


def _unsupported(values: Sequence[Value], sources: Sources, kinds: Sequence[str]) -> list[Value]:
    seen: set[str] = set()
    out = []
    for value in values:
        if value.kind in kinds and not sources.supports(value) and value.text not in seen:
            seen.add(value.text)
            out.append(value)
    return out


def _describe(values: Sequence[Value]) -> str:
    return ", ".join(f"{v.text}({_KIND_LABEL[v.kind]})" for v in values)


def check_values(
    draft: Draft, required_slots: Sequence[str], values: Sequence[Value], sources: Sources
) -> CheckResult:
    problems = []
    invented = _unsupported(values, sources, _VALUE_KINDS)
    if invented:
        problems.append("근거·조회값에 없는 값: " + _describe(invented))
    answer_numbers: set[float] = set()
    for m in _NUMBER.finditer(_nfkc(draft.text)):
        answer_numbers |= number_values(m.group(0))
    for slot in required_slots:
        slot_value = str(draft.slots.get(slot, "") or "")
        slot_numbers = [number_values(m.group(0)) for m in _NUMBER.finditer(_nfkc(slot_value))]
        if slot_numbers and not any(nums & answer_numbers for nums in slot_numbers):
            problems.append(f"슬롯 {slot} 값({slot_value})이 답변에 없거나 다르게 씀")
    if problems:
        return CheckResult(name="values", passed=False, reason="; ".join(problems))
    return CheckResult(name="values", passed=True)


def check_specs(values: Sequence[Value], sources: Sources) -> CheckResult:
    invented = _unsupported(values, sources, _SPEC_KINDS)
    if invented:
        return CheckResult(
            name="specs", passed=False, reason="문의·근거에 없는 사양: " + _describe(invented)
        )
    return CheckResult(name="specs", passed=True)


# 4 language ---------------------------------------------------------------------------------

_SCRIPT_OF = {"th": ("THAI",), "ar": ("ARABIC",), "ru": ("CYRILLIC",), "ko": ("HANGUL",),
              "ja": ("HIRAGANA", "KATAKANA"), "zh": ("CJK",)}  # fmt: skip
_WIDE = ("CJK", "HIRAGANA", "KATAKANA", "HANGUL", "THAI")  # 한 글자가 라틴 몇 글자 몫
LANGUAGE_CODES = ("en", "es", "fr", "th", "it", "id", "zh", "tr", "ar", "ru", "vi", "pt", "de",
                  "ja", "pl", "ko")  # fmt: skip
LANGUAGE_GAP = 0.3  # 1등 언어 확신도 − 고객 언어 확신도가 이 이상이고
LANGUAGE_WANT_MAX = 0.2  # 고객 언어 확신도가 이 미만이면 다른 언어로 본다
_MIN_DETECT_CHARS = 12  # 옮긴 구절을 빼고 남은 글이 이보다 짧으면 판단하지 않는다
_MIN_SENTENCE_CHARS = 25  # 문장 단위 판단의 최소 길이
_NON_LATIN = frozenset(_SCRIPT_OF)


@lru_cache
def _detector() -> Any:
    from lingua import IsoCode639_1, Language, LanguageDetectorBuilder

    languages = [
        Language.from_iso_code_639_1(getattr(IsoCode639_1, c.upper())) for c in LANGUAGE_CODES
    ]
    return LanguageDetectorBuilder.from_languages(*languages).with_low_accuracy_mode().build()


_COPY_MAX_WORDS = 6


@lru_cache(maxsize=64)
def _source_ngrams(source_text: str) -> frozenset[tuple[str, ...]]:
    """근거 글의 2~6 단어 구절 (소문자). 같은 근거로 문장마다 부르므로 캐시한다."""
    words = [w.lower() for w in _words(_nfkc(source_text))]
    return frozenset(
        tuple(words[i : i + n])
        for n in range(2, _COPY_MAX_WORDS + 1)
        for i in range(len(words) - n + 1)
    )


def strip_copied(text: str, source_text: str) -> str:
    """근거·문의에서 그대로 옮긴 2~6 단어 구절과 ID·숫자를 뺀 나머지 글."""
    text = _ID.sub(" ", _nfkc(text))
    ngrams = _source_ngrams(source_text)
    original = _words(text)
    words = [w.lower() for w in original]
    keep = [True] * len(words)
    for i in range(len(words)):
        for j in range(min(len(words), i + _COPY_MAX_WORDS), i + 1, -1):
            if tuple(words[i:j]) in ngrams:
                for k in range(i, j):
                    keep[k] = False
                break
    return " ".join(w for w, k in zip(original, keep, strict=True) if k)


# 고유 문자 → 언어. 가나가 있으면 한자가 섞여도 일본어라 가나를 한자보다 먼저 본다
_SCRIPT_LANGUAGE = (
    ("HANGUL", "ko"),
    ("HIRAGANA", "ja"),
    ("KATAKANA", "ja"),
    ("CJK", "zh"),
    ("THAI", "th"),
    ("ARABIC", "ar"),
    ("CYRILLIC", "ru"),
)


def detect_language(text: str, default: str = "en") -> str:
    """고객 글 → 언어 코드 (LANGUAGE_CODES 중). 고객 언어를 모를 때 쓴다 (챗봇·웹 문의서).

    고유 문자(한글·가나·한자 …)가 있으면 그 언어 — 제품 코드가 섞인 짧은 말도 정해진다.
    그 밖은 lingua. 글자가 거의 없거나 판단하지 못하면 default.
    """
    rest = strip_copied(text, "")  # 제품 코드·숫자를 뺀 글
    scripts = {_script(ch) for ch in rest if ch.isalpha()}
    for script, code in _SCRIPT_LANGUAGE:
        if script in scripts:
            return code
    if sum(ch.isalpha() for ch in rest) < 2:
        return default
    detected = _detector().detect_language_of(rest)
    return detected.iso_code_639_1.name.lower() if detected is not None else default


def detect_mismatch(text: str, language: str, source_text: str = "") -> str | None:
    """고객 언어와 다르면 그 언어(또는 문자 종류)를, 같거나 판단할 수 없으면 None."""
    language = (language or "").lower().split("-")[0]
    rest = strip_copied(text, source_text)
    weights: dict[str, int] = {}
    for ch in rest:
        if ch.isalpha():
            script = _script(ch)
            weights[script] = weights.get(script, 0) + (3 if script in _WIDE else 1)
    total = sum(weights.values())
    if not total:
        return None
    if language in _SCRIPT_OF:
        wanted = sum(weights.get(s, 0) for s in _SCRIPT_OF[language])
        kana = weights.get("HIRAGANA", 0) + weights.get("KATAKANA", 0)
        if language == "zh" and kana:
            return "ja"
        if language == "ja" and kana:
            wanted += weights.get("CJK", 0)
        if wanted / total >= 0.5:
            return None
        top = max(weights, key=lambda s: weights[s])
        return _script_language(top)
    other = sum(v for s, v in weights.items() if s not in ("LATIN", "OTHER"))
    if other / total >= 0.1:
        return _script_language(max((s for s in weights if s not in ("LATIN", "OTHER")),
                                    key=lambda s: weights[s]))  # fmt: skip
    if language not in LANGUAGE_CODES:
        return None
    if len(rest) >= _MIN_DETECT_CHARS:
        confidence = {
            cv.language.iso_code_639_1.name.lower(): cv.value
            for cv in _detector().compute_language_confidence_values(rest)
        }
        top = max(confidence, key=lambda c: confidence[c])
        want = confidence.get(language, 0.0)
        if top != language and confidence[top] - want >= LANGUAGE_GAP and want < LANGUAGE_WANT_MAX:
            return top
    return _stopword_vote(rest, language)


# 짧은 글("Terlampir datasheet untuk …")은 통계 감지가 약해 기능어 수로 한 번 더 본다.
# 다른 언어 기능어가 고객 언어 기능어보다 STOPWORD_MARGIN 개 이상 많으면 그 언어로 본다.
STOPWORD_MARGIN = 3
STOPWORDS: dict[str, frozenset[str]] = {
    lang: frozenset(words.split())
    for lang, words in {
        "en": "the a an of for to and is are with your our we you please find attached this that "
        "in on be will can from as by it at",
        "es": "el la los las de del para y es son con su sus nuestro le les por favor adjuntamos "
        "se que en un una al como",
        "fr": "le la les de des du pour et est sont avec votre vos nous veuillez ci-joint joint ce "
        "cette en un une au aux que",
        "it": "il lo la i gli le di del della per e è sono con suo sua nostro in allegato un una "
        "al che si",
        "pt": "o a os as de do da dos das para e é são com seu sua nosso segue em anexo um uma ao "
        "que por favor",
        "de": "der die das den dem des für und ist sind mit ihr ihre wir sie bitte anbei ein eine "
        "im zu von auf",
        "pl": "w z do i jest są dla na od przez prosimy załączamy naszym ten ta to oraz się",
        "tr": "ve bir bu için ile olan da de ektedir lütfen sizin bizim olarak ise",
        "id": "dan yang untuk dengan dari ini itu adalah kami anda terlampir mohon pada ke dalam",
        "vi": "và của cho với là các những này được chúng tôi quý khách xin gửi kèm theo",
    }.items()
}


def _stopword_vote(rest: str, language: str) -> str | None:
    if language not in STOPWORDS:
        return None
    words = [w.lower() for w in _words(rest)]
    hits = {lang: sum(w in stop for w in words) for lang, stop in STOPWORDS.items()}
    top = max((lang for lang in hits if lang != language), key=lambda lang: hits[lang])
    return top if hits[top] - hits[language] >= STOPWORD_MARGIN else None


def _script_language(script: str) -> str:
    return {"THAI": "th", "ARABIC": "ar", "CYRILLIC": "ru", "HANGUL": "ko", "HIRAGANA": "ja",
            "KATAKANA": "ja", "CJK": "zh", "LATIN": "en"}.get(script, script.lower())  # fmt: skip


def check_language(draft: Draft, language: str, sources: Sources) -> CheckResult:
    found = detect_mismatch(draft.text, language, sources.text)
    mixed = []
    if not found:
        # 전체는 맞는데 한 문장만 영어(또는 다른 문자)로 쓴 경우. 짧은 문장은 가까운 언어끼리
        # (es·pt·it) 헷갈리므로 문장 단위로는 영어·문자 종류만 본다.
        wanted = (language or "").lower().split("-")[0]
        for i, sentence in enumerate(split_sentences(draft.text), 1):
            if len(strip_copied(sentence, sources.text)) < _MIN_SENTENCE_CHARS:
                continue
            other = detect_mismatch(sentence, language, sources.text)
            if other and (other == "en" or other in _NON_LATIN or wanted in _NON_LATIN):
                mixed.append(f"{i}번 문장({other}): {_snippet(sentence)}")
    if found:
        return CheckResult(
            name="language",
            passed=False,
            reason=f"답변 언어가 검토 대상 언어({language})와 다름: {found}로 보임",
        )
    if mixed:
        return CheckResult(
            name="language",
            passed=False,
            reason=f"검토 대상 언어({language})가 아닌 문장: " + "; ".join(mixed),
        )
    return CheckResult(name="language", passed=True)


# 5 banned -----------------------------------------------------------------------------------

# 진단형: 원인 단정. tickets 실제 회신(사람이 진단 후 쓴 글)의 언어별 표현에서 뽑았다.
CAUSE_ASSERTIONS: dict[str, tuple[str, ...]] = {
    "en": (
        r"\b(?:the\s+)?root\s+cause\s+(?:is|was)\b",
        r"\bthe\s+cause\s+(?:is|was)\b",
        r"(?:^|\.\s*)(?:root\s+)?cause\s*:",
        r"(?:^|\.\s*)diagnosis\s*:",
        r"\bthe\s+diagnosis\s+(?:indicates|shows|confirms)\b",
        r"\b(?:is|was|were|has\s+been)\s+caused\s+by\b",
        r"\bthe\s+(?:issue|problem|fault)\s+(?:is|was)\s+due\s+to\b",
        r"\bhas\s+been\s+identified\s+as\b",
    ),
    "es": (
        r"\bla\s+causa(?:\s+raíz)?\s+(?:es|fue)\b",
        r"(?:^|\.\s*)causa\s*:",
        r"(?:^|\.\s*)diagnóstico\s*:",
        r"\bel\s+diagnóstico\s+indica\b",
        r"\bse\s+debía\s+a\b",
        r"\b(?:fue|es)\s+causad[oa]\s+por\b",
    ),
    "fr": (
        r"\bla\s+cause(?:\s+racine)?\s+(?:est|était)\b",
        r"(?:^|\.\s*)cause\s*:",
        r"(?:^|\.\s*)diagnostic\s*:",
        r"\ble\s+diagnostic\s+indique\b",
        r"\bétait\s+dû\s+à\b",
        r"\best\s+dû\s+à\b",
    ),
    "it": (
        r"\bla\s+causa(?:\s+principale)?\s+(?:è|era)\b",
        r"(?:^|\.\s*)causa\s*:",
        r"(?:^|\.\s*)diagnosi\s*:",
        r"\bla\s+diagnosi\s+indica\b",
        r"\b(?:era|è)\s+causat[oa]\s+da\b",
    ),
    "pt": (
        r"\ba\s+causa(?:\s+raiz)?\s+(?:é|foi)\b",
        r"(?:^|\.\s*)causa\s*:",
        r"(?:^|\.\s*)diagnóstico\s*:",
        r"\bo\s+diagnóstico\s+indica\b",
        r"\b(?:foi|é)\s+causad[oa]\s+por\b",
    ),
    "de": (
        r"\bdie\s+Ursache\s+(?:ist|war)\b",
        r"(?:^|\.\s*)Ursache\s*:",
        r"(?:^|\.\s*)Diagnose\s*:",
        r"\bdie\s+Diagnose\s+(?:weist|zeigt)\b",
        r"\bUrsache\s+des\s+Problems\b",
        r"\bverursacht\s+durch\b",
    ),
    "pl": (
        r"\bprzyczyną\s+(?:jest|było)\b",
        r"(?:^|\.\s*)przyczyna\s*:",
        r"(?:^|\.\s*)diagnoza\s*:",
        r"\bdiagnoza\s+wskazuje\b",
        r"\bprzyczyna\s+problemu\b",
        r"\bspowodowan[aey]\s+przez\b",
    ),
    "tr": (
        r"\bkök\s+neden\b",
        r"(?:^|\.\s*)neden\s*:",
        r"(?:^|\.\s*)teşhis\s*:",
        r"\bteşhis\b.{0,40}\bişaret\s+ediyor\b",
        r"\bsorunun\s+nedeni\b",
    ),
    "id": (
        r"\bakar\s+penyebab(?:nya)?\s+adalah\b",
        r"(?:^|\.\s*)penyebab\s*:",
        r"(?:^|\.\s*)diagnosis\s*:",
        r"\bdiagnosis\s+menunjukkan\b",
        r"\bdisebabkan\s+oleh\b",
    ),
    "vi": (
        r"\bnguyên\s+nhân\s+gốc\s+là\b",
        r"\bnguyên\s+nhân\s+là\b",
        r"(?:^|\.\s*)nguyên\s+nhân\s*:",
        r"(?:^|\.\s*)chẩn\s+đoán\s*:",
        r"\bkết\s+quả\s+chẩn\s+đoán\s+cho\s+thấy\b",
        r"\bsự\s+cố\s+do\b",
    ),
    "ru": (
        r"первопричин",
        r"\bпричина\s*:",
        r"\bдиагноз\s*:",
        r"диагностика\s+указывает",
        r"\bпричина\s+проблемы\b",
        r"\bвызван[ао]?\b",
    ),
    "ar": (r"السبب\s+الجذري", r"السبب\s*:", r"التشخيص\s*:", r"يشير\s+التشخيص", r"سبب\s+المشكلة"),
    "th": (r"สาเหตุหลักคือ", r"สาเหตุ\s*:", r"ผลการวิเคราะห์\s*:", r"ผลการวิเคราะห์ชี้ว่า", r"ปัญหาเกิดจาก"),
    "zh": (
        r"根本原因是",
        r"原因[：:]",
        r"诊断结果[：:]",
        r"诊断结果显示",
        r"问题的原因是",
        r"是由.{1,30}(?:引起|造成)的",
    ),
    "ja": (
        r"根本原因は",
        r"原因[：:]",
        r"診断結果[：:]",
        r"と判断いたしました",
        r"本件の原因は",
        r"が原因です",
    ),
    "ko": (
        r"근본\s*원인은",
        r"원인은\s*.{1,40}(?:입니다|였습니다)",
        r"원인\s*[:：]",
        r"진단\s*결과\s*[:：]",
        r"(?:로|으로)\s*인해\s*발생했습니다",
        r"고장으로\s*확인",
    ),
}
# 정책형: 이 건에 대한 승인·반려 판정. 정책 조항 일반 문장("Returns are accepted within 30 days",
# "After 30 days: not accepted")은 판정이 아니다
# → 주어가 이 건(your/this, RMA)이거나 완료형만 잡는다.
DECISIONS: dict[str, tuple[str, ...]] = {
    "en": (
        r"\bour\s+inspection\s+(?:found|revealed|showed|confirmed)\b",
        r"\bwhich\s+is\s+not\s+covered\b",
        r"\b(?:your|this|the)\s+(?:return|claim|request|warranty\s+claim|replacement|refund|exchange|repair)"
        r"\s+(?:is|has\s+been|was)\s+(?:approved|accepted|rejected|declined|denied)\b",
        r"\b(?:return|claim|request)\s+(?:approved|accepted|rejected|declined)\b",
        r"\bapproved\s+under\b",
        r"\bwe\s+(?:have\s+)?(?:approved|accepted|rejected|declined|denied)\b",
        r"\bwe\s+(?:approve|reject|decline|deny)\s+(?:your|the|this)\b",
        r"\b(?:cannot|can\s*not|are\s+unable\s+to|will\s+not)\s+accept\s+(?:the|your|this)\b",
        r"\b(?:your|this|the)\s+(?:unit|claim|damage|product|case)\s+is\s+not\s+covered\b",
        r"\bRMA\b.{0,30}\b(?:has\s+been|was|is)\s+issued\b",
        r"\bwe\s+have\s+issued\b",
        r"\bcredit\s+note\s+will\s+be\s+issued\b",
    ),
    "es": (
        r"\bhemos\s+(?:aprobado|aceptado|rechazado)\b",
        r"\bnuestra\s+inspección\s+(?:detectó|encontró|reveló|identificó)\b",
        r"\b(?:ha|han)\s+sido\s+(?:aprobad|aceptad|rechazad|denegad)[oa]s?\b",
        r"\b(?:fue|fueron|queda|quedan)\s+(?:aprobad|aceptad|rechazad|denegad)[oa]s?\b",
        r"\b(?:devolución|reclamación|solicitud|garantía)\s+(?:aprobad|aceptad|rechazad)a\b",
        r"\bno\s+podemos\s+aceptar\s+(?:la|su|esta|el|este)\b",
    ),
    "fr": (
        r"\bnous\s+avons\s+(?:approuvé|accepté|refusé)\b",
        r"\bnotre\s+inspection\s+a\s+(?:révélé|constaté|montré)\b",
        r"\b(?:retour|demande|réclamation)\s+(?:est\s+)?(?:accepté|approuvé|refusé)e?\b",
        r"\b(?:a|ont)\s+été\s+(?:accepté|approuvé|refusé)e?s?\b",
        r"\bne\s+pouvons\s+pas\s+accepter\s+(?:le|la|votre|ce|cette)\b",
    ),
    "it": (
        r"\babbiamo\s+(?:approvato|accettato|rifiutato)\b",
        r"\bla\s+nostra\s+ispezione\s+ha\s+(?:rilevato|riscontrato)\b",
        r"\b(?:reso|richiesta|reclamo)\s+(?:è\s+stat[oa]\s+)?(?:approvat|accettat|rifiutat|respint)[oa]\b",
        r"\b(?:è|sono)\s+stat[oaie]\s+(?:approvat|accettat|rifiutat|respint)[oaie]\b",
        r"\bnon\s+possiamo\s+accettare\s+(?:il|la|lo|questo|questa)\b",
    ),
    "pt": (
        r"\b(?:aprovamos|aceitamos|recusamos)\b",
        r"\bnossa\s+inspeção\s+(?:identificou|encontrou|revelou)\b",
        r"\b(?:devolução|solicitação|reclamação)\s+(?:foi\s+)?(?:aprovad|aceit|recusad)a\b",
        r"\bfo(?:i|ram)\s+(?:aprovad|aceit|recusad)[oa]s?\b",
        r"\bnão\s+podemos\s+aceitar\s+(?:a|o|esta|este|sua|seu)\b",
    ),
    "de": (
        r"\bhaben\b.{0,40}\b(?:genehmigt|abgelehnt)\b",
        r"\bunsere\s+(?:Prüfung|Inspektion)\s+(?:hat|ergab)\b",
        r"\b(?:wurde|wurden)\b.{0,40}\b(?:genehmigt|abgelehnt|anerkannt)\b",
        r"\bRücksendung\b.{0,40}\bgenehmigt\b",
        r"\bkönnen\s+wir\b.{0,40}\bnicht\s+annehmen\b",
    ),
    "pl": (
        r"\bnasza\s+inspekcja\s+wykazała\b",
        r"\b(?:zwrot|reklamacja|wniosek)\s+(?:został[ao]?\s+)?(?:zatwierdzon|zaakceptowan|odrzucon)\w*",
        r"\b(?:został[ao]?|zostały)\s+(?:zatwierdzon|zaakceptowan|odrzucon)\w*",
        r"\bzatwierdz(?:iliśmy|ono)\b",
        r"\bnie\s+możemy\s+przyjąć\b",
    ),
    "tr": (
        r"\bonayladık\b",
        r"\breddettik\b",
        r"\bincelememiz(?:de)?\b",
        r"\bonayland[ıi]\b",
        r"\bonaylanmıştır\b",
        r"\bkabul\s+edildi\b",
        r"\breddedildi\b",
        r"\bkabul\s+edemiyoruz\b",
    ),
    "id": (
        r"\bmenyetujui\b",
        r"\bmenolak\b",
        r"\bpemeriksaan\s+kami\s+menemukan\b",
        r"\bdisetujui\b",
        r"\bditolak\b",
        r"\btidak\s+dapat\s+menerima\s+pengembalian\b",
    ),
    "vi": (
        r"qua\s+kiểm\s+tra,?\s+chúng\s+tôi\s+phát\s+hiện",
        r"được\s+chấp\s+thuận",
        r"đã\s+chấp\s+thuận",
        r"đã\s+phê\s+duyệt",
        r"\bbị\s+từ\s+chối\b",
        r"không\s+thể\s+chấp\s+nhận",
    ),
    "ru": (
        r"\bодобрил[иа]?\b",
        r"\bотклонил[иа]?\b",
        r"\bнаша\s+проверка\s+(?:выявила|показала)\b",
        r"\bодобрен[аоы]?\b",
        r"\bотклонен[аоы]?\b",
        r"не\s+можем\s+принять",
    ),
    "ar": (
        r"وافقنا",
        r"كشف\s+الفحص",
        r"تمت\s+الموافقة",
        r"تم\s+رفض",
        r"لا\s+يمكننا\s+قبول",
        r"عدم\s+تمكننا\s+من\s+قبول",
    ),
    "th": (
        r"ได้อนุมัติ",
        r"จากการตรวจสอบ\s*เราพบ",
        r"อนุมัติ.{0,60}แล้ว",
        r"ได้รับการอนุมัติ",
        r"ไม่สามารถรับคืน",
        r"ปฏิเสธ",
    ),
    "zh": (
        r"经检查[，,]?\s*发现",
        r"已.{0,15}批准",
        r"批准保修",
        r"予以批准",
        r"不予",
        r"拒绝",
        r"无法接受",
    ),
    "ja": (
        r"点検の結果",
        r"検査の結果",
        r"承認いたしました",
        r"承認されました",
        r"承認します",
        r"却下",
        r"お受けできません",
    ),
    "ko": (
        r"점검\s*결과",
        r"검사\s*결과",
        r"승인(?:되었|됐|했|합니다|해\s*드립니다|하였)",
        r"반려(?:되었|됐|했|합니다|하였)",
        r"거절(?:되었|됐|했|합니다)",
        r"(?:반품|교환|환불|수리)(?:이|가|은|는)?\s*불가(?:합니다|능합니다)",
    ),
}
# 추정 표현: 문장에 있으면 원인 단정이 아니다 (고객 언어와 영어 것만 본다)
HEDGES: dict[str, str] = {
    "en": r"\b(?:may|might|could|possible|possibly|potential|likely|probabl[ey]|suspect\w*"
    r"|candidates?|typically)\b",
    "es": r"\b(?:posibles?|podría|puede|pueden|probablemente|potencial(?:es)?)\b",
    "fr": r"\b(?:pourrai(?:t|ent)|peu(?:t|vent)|possibles?|probablement|potentiel(?:le)?s?)\b",
    "it": r"\b(?:possibil[ei]|potrebbe(?:ro)?|può|possono|probabilmente)\b",
    "pt": r"\b(?:possíve(?:l|is)|poderia|pode|podem|provavelmente)\b",
    "de": r"\b(?:mögliche[nr]?|möglicherweise|könnte|kann|können|wahrscheinlich)\b",
    "pl": r"\b(?:możliw\w*|może|mogą|prawdopodobn\w*)\b",
    "tr": r"\b(?:olası|muhtemel\w*|olabilir)\b",
    "id": r"\b(?:kemungkinan|mungkin|dapat)\b",
    "vi": r"có\s+thể|khả\s+năng",
    "ru": r"возможн\w*|\bможет\b|вероятн\w*",
    "ar": r"محتمل|ربما|قد\s",
    "th": r"อาจ|เป็นไปได้",
    "zh": r"可能",
    "ja": r"可能性|考えられ",
    "ko": r"가능성|가능한|수\s*있|추정|의심|후보",
}
# 조건 표현: 문장에 있으면 승인·반려 판정이 아니다 ("승인되면", "once approved").
# 언어마다 따로 둔다 (이탈리아어 조건 "se" 가 스페인어 "Se ha aprobado" 를 빼면 안 된다).
CONDITIONS: dict[str, str] = {
    "en": r"\b(?:if|once|upon|subject\s+to|pending|whether|until|requires?"
    r"|needs?\s+to\s+be|can\s+only)\b",
    "es": r"\b(?:si|una\s+vez|tras|sujet[oa]\s+a|pendiente)\b",
    "fr": r"\b(?:si|une\s+fois|sous\s+réserve)\b",
    "it": r"\b(?:se|una\s+volta|previa|soggett[oa])\b",
    "pt": r"\b(?:caso|uma\s+vez|sujeit[oa])\b",
    "de": r"\b(?:wenn|falls|sobald|vorbehaltlich)\b",
    "pl": r"\b(?:jeśli|jeżeli|o\s+ile|pod\s+warunkiem)\b",
    "tr": r"\b(?:eğer|halinde|takdirde)\b",
    "id": r"\b(?:jika|apabila|setelah)\b",
    "vi": r"\bnếu\b|sau\s+khi",
    "ru": r"\bесли\b|при\s+условии",
    "ar": r"إذا|عند",
    "th": r"หาก|ถ้า",
    "zh": r"如果|若|一旦|批准后|审核后",
    "ja": r"場合|次第|承認後",
    "ko": r"(?:되면|하면|경우|여부|검토\s*후)",
}
_CAUSE = [re.compile(p, re.I) for ps in CAUSE_ASSERTIONS.values() for p in ps]
_DECISION = [re.compile(p, re.I) for ps in DECISIONS.values() for p in ps]


def _exempt(sentence: str, table: dict[str, str], language: str) -> bool:
    """고객 언어(와 영어)의 추정·조건 표현이 문장에 있는가."""
    languages = {(language or "en").lower().split("-")[0], "en"}
    return any(re.search(table[lang], sentence, re.I) for lang in languages if lang in table)


def find_banned(
    text: str, category: Category | None, language: str = "en"
) -> list[tuple[int, str, str]]:
    """(문장 번호, 종류, 걸린 표현). 진단형은 원인 단정, 정책형은 승인·반려 판정만 본다."""
    bundle = BUNDLE_OF.get(category) if category else None
    if bundle == Bundle.DIAGNOSIS:
        patterns, exempt, kind = _CAUSE, HEDGES, "원인 단정"
    elif bundle == Bundle.POLICY:
        patterns, exempt, kind = _DECISION, CONDITIONS, "승인·반려 판정"
    else:
        return []
    found = []
    for i, sentence in enumerate(split_sentences(text), 1):
        if _exempt(sentence, exempt, language):
            continue
        for pattern in patterns:
            m = pattern.search(sentence)
            if m:
                found.append((i, kind, m.group(0).strip()))
                break
    return found


def check_banned(draft: Draft, category: Category, language: str = "en") -> CheckResult:
    found = find_banned(draft.text, category, language)
    if found:
        hint = (
            "원인 후보로 쓰고 확인 절차를 안내"
            if found[0][1] == "원인 단정"
            else "승인·반려는 상담원이 정한다고 안내"
        )
        listed = "; ".join(f"{i}번 문장 '{phrase}'" for i, _, phrase in found)
        return CheckResult(
            name="banned", passed=False, reason=f"{found[0][1]} 표현: {listed} ({hint})"
        )
    return CheckResult(name="banned", passed=True)


# 6 grounding --------------------------------------------------------------------------------

_GROUNDING_RULES = (
    "Count as supported: greetings, thanks, apologies, offers to help, requests for more "
    "information, procedural next steps that make no factual claim, and statements that the "
    "references do not contain the information.\n"
    "Count as NOT supported: any value, specification, certification, compatibility, cause, "
    "date, price, lead time, warranty term, approval or commitment that the references, the "
    "lookup values and the customer's own inquiry do not state."
)


def _context(inquiry_text: str, evidence: Sequence[Evidence], draft: Draft) -> str:
    refs = [
        f"[{i}] {e.doc_id}{'#' + e.section if e.section else ''} ({e.source}): "
        f"{e.text[:REFERENCE_CHARS]}"
        for i, e in enumerate(evidence, 1)
    ]
    slots = [f"- {k}: {v}" for k, v in draft.slots.items() if str(v).strip()]
    return (
        "References:\n" + ("\n".join(refs) or "(none)") + "\n\n"
        "Lookup values from our reference tables (authoritative):\n"
        + ("\n".join(slots) or "(none)")
        + f"\n\nCustomer inquiry:\n{inquiry_text.strip()}"
    )


def grounding_prompt_all(context: str, sentences: Sequence[str]) -> str:
    numbered = "\n".join(f"{i}. {s}" for i, s in enumerate(sentences, 1))
    return (
        "You check a customer-support reply against its references before it is sent.\n"
        f"{_GROUNDING_RULES}\n\n{context}\n\nReply (numbered sentences):\n{numbered}\n\n"
        "Question: is EVERY sentence of the reply supported? Answer yes or no."
    )


def grounding_prompt_sentence(context: str, sentences: Sequence[str], index: int) -> str:
    return (
        "You check one sentence of a customer-support reply against its references.\n"
        f"{_GROUNDING_RULES}\n\n{context}\n\nFull reply for context:\n"
        + " ".join(sentences)
        + f"\n\nSentence {index + 1}: {sentences[index]}\n\n"
        "Question: is this sentence supported? Answer yes or no."
    )


def check_grounding(
    draft: Draft,
    inquiry_text: str,
    evidence: Sequence[Evidence],
    llm: LLMRouter,
) -> CheckResult:
    sentences = split_sentences(draft.text)
    if not sentences:
        return CheckResult(name="grounding", passed=False, reason="답변이 비어 있음")
    context = _context(inquiry_text, evidence, draft)
    try:
        overall = llm.judge(GROUNDING_TASK, grounding_prompt_all(context, sentences), ["yes", "no"])
    except Exception as e:
        return _grounding_error(e)
    if overall.model == FakeJudge.name:
        return CheckResult(name="grounding", passed=True, reason="판단 모델 꺼짐: 근거 검증 생략")
    if overall.answer == "yes" and overall.confidence >= GROUNDING_MIN_CONFIDENCE:
        return CheckResult(name="grounding", passed=True)

    def judge_sentence(i: int) -> Any:
        prompt = grounding_prompt_sentence(context, sentences, i)
        return llm.judge(GROUNDING_TASK, prompt, ["yes", "no"])

    # 문의 단위 Langfuse trace(ticket_scope)를 스레드에도 넘긴다
    trace_context = contextvars.copy_context()
    try:
        with ThreadPoolExecutor(min(GROUNDING_WORKERS, len(sentences))) as pool:
            results = list(
                pool.map(
                    lambda i: trace_context.copy().run(judge_sentence, i), range(len(sentences))
                )
            )
    except Exception as e:
        return _grounding_error(e)

    unsupported = [
        f"{i}번 문장 근거 없음: {_snippet(s)}"
        for i, (s, r) in enumerate(zip(sentences, results, strict=True), 1)
        if r.answer == "no"
    ]
    uncertain = [
        f"{i}번 문장 근거 확인 불확실: {_snippet(s)}"
        for i, (s, r) in enumerate(zip(sentences, results, strict=True), 1)
        if r.answer == "yes" and r.confidence < GROUNDING_MIN_CONFIDENCE
    ]
    if unsupported or uncertain:
        return CheckResult(
            name="grounding", passed=False, reason="; ".join(unsupported + uncertain)
        )
    return CheckResult(name="grounding", passed=True)


def _grounding_error(error: Exception) -> CheckResult:
    return CheckResult(
        name="grounding",
        passed=False,
        reason=f"근거 검증 호출 실패({type(error).__name__}): 상담원 확인 필요",
    )


# ⑩ ------------------------------------------------------------------------------------------


def verify(
    draft: Draft,
    category: Category,
    required_slots: tuple[str, ...],
    inquiry_text: str,
    language: str,
    evidence: list[Evidence],
    llm: LLMRouter,
) -> list[CheckResult]:
    """점검 1~6 결과 목록. 위 '할 일' 참고."""
    slots = check_slots(draft, required_slots)
    if not draft.text.strip():
        return [slots, CheckResult(name="not_empty", passed=False, reason="답변이 비어 있음")]
    if draft.model == FakeWriter.name:
        return [slots, CheckResult(name="content", passed=True, reason="LLM 꺼짐: 내용 점검 생략")]

    sources = build_sources(inquiry_text, evidence, draft)
    values = extract_values(draft.text)
    results = [
        slots,
        check_values(draft, required_slots, values, sources),
        check_specs(values, sources),
        check_language(draft, language, sources),
        check_banned(draft, category, language),
    ]
    if all(r.passed for r in results):
        results.append(check_grounding(draft, inquiry_text, evidence, llm))
    return results
