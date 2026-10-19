"""⑩ 자동 점검(검증) 에이전트 (CSA-31 · 담당 김동규).

코드 점검 1~5를 먼저 하고, 다 통과하면 LLM 근거 검증(6)을 부른다. 실패 사유는 그대로
답변 작성에 넘겨 재작성한다 (최대 2회, S-06). 그래도 실패면 보류 (P-03).
"""

import re

from cs_agent.domain import BUNDLE_OF, Bundle, Category
from cs_agent.llm.router import LLMRouter
from cs_agent.schemas import CheckResult, Draft, Evidence

_DIAGNOSIS_BANNED = ("the cause is", "definitely caused", "원인은 확실히")
_POLICY_BANNED = ("approved", "rejected", "승인되었습니다", "반려되었습니다")
_SPEC_TOKEN_RE = re.compile(r"\b(\d+(?:\.\d+)?\s?(?:kA|kV|A|V|kW|kVA)|IEC\s?\d+|UL\s?\d+)\b")


def _result(name: str, bad: list, reason: str) -> CheckResult:
    return CheckResult(name=name, passed=not bad, reason=reason if bad else "")


def check_slots(draft: Draft, required: tuple[str, ...]) -> CheckResult:
    missing = [s for s in required if not draft.slots.get(s)]
    return _result("slots", missing, f"슬롯 누락: {missing}")


def check_values(draft: Draft) -> CheckResult:
    bad = [v for v in draft.slots.values() if v and v not in draft.text]
    return _result("values", bad, f"조회값과 다름: {bad}")


def check_unrequested_specs(
    draft: Draft, inquiry_text: str, evidence: list[Evidence]
) -> CheckResult:
    """고객이 말하지 않고 근거에도 없는 사양을 넣었는가 (C-05)."""
    allowed = " ".join([inquiry_text, *draft.slots.values(), *(e.text for e in evidence)])
    allowed = allowed.replace(" ", "")
    extra = [t for t in _SPEC_TOKEN_RE.findall(draft.text) if t.replace(" ", "") not in allowed]
    return _result("specs", extra, f"근거 없는 사양: {extra}")


def check_language(draft: Draft, language: str) -> CheckResult:
    # TODO(CSA-31): 언어 감지 라이브러리로 교체 (C-02)
    has_hangul = bool(re.search(r"[가-힣]", draft.text))
    passed = has_hangul if language == "ko" else True
    return CheckResult(name="language", passed=passed, reason="" if passed else "답변 언어 불일치")


def check_banned(draft: Draft, category: Category) -> CheckResult:
    bundle = BUNDLE_OF[category]
    banned = {Bundle.DIAGNOSIS: _DIAGNOSIS_BANNED, Bundle.POLICY: _POLICY_BANNED}.get(bundle, ())
    hits = [b for b in banned if b in draft.text.lower()]
    return _result("banned", hits, f"금지 표현: {hits}")


def check_grounding(draft: Draft, evidence: list[Evidence], llm: LLMRouter) -> CheckResult:
    if not llm.enabled:
        return CheckResult(
            name="grounding", passed=bool(evidence), reason="" if evidence else "근거 없음"
        )
    sources = "\n".join(f"[{e.doc_id} {e.section}] {e.text}" for e in evidence)
    j = llm.judge(
        "verify_grounding",
        f"답변의 모든 문장이 근거에서 나왔는가?\n근거:\n{sources}\n\n답변:\n{draft.text}",
        ["yes", "no"],
    )
    return CheckResult(
        name="grounding", passed=j.answer == "yes", reason=f"confidence={j.confidence}"
    )


def verify(
    draft: Draft,
    category: Category,
    required_slots: tuple[str, ...],
    inquiry_text: str,
    language: str,
    evidence: list[Evidence],
    llm: LLMRouter,
) -> list[CheckResult]:
    checks = [
        check_slots(draft, required_slots),
        check_values(draft),
        check_unrequested_specs(draft, inquiry_text, evidence),
        check_language(draft, language),
        check_banned(draft, category),
    ]
    if all(c.passed for c in checks):
        checks.append(check_grounding(draft, evidence, llm))
    return checks
