import csv
import random
import threading

import pytest

from cs_agent.agents import verification as V
from cs_agent.config import REPO_ROOT, Settings
from cs_agent.domain import Category
from cs_agent.llm.clients import FakeWriter, Judgement
from cs_agent.llm.router import LLMRouter
from cs_agent.schemas import Draft, Evidence

DS_EVIDENCE = Evidence(
    source="docs",
    doc_id="DS-MCCB-ABS-403c",
    section="2.1",
    text=(
        "| Rated current (In) | 250, 300, 350, 400 A |\n"
        "| Rated operational voltage (Ue) | AC 690 V max |\n"
        "| Ultimate breaking capacity Icu at AC 415 V | 50 kA |\n"
        "Standards: IEC 60947-2. Certifications: CE, CB, KC."
    ),
    metadata={"doc_type": "DS", "product_code": "MCCB-ABS-403c", "family": "LV_BREAKER"},
)
INQUIRY = "What is the breaking capacity of the MCCB 400AF at 415 V?"
GOOD = (
    "Thank you for your inquiry. The ultimate breaking capacity Icu of MCCB 400AF at AC 415 V "
    "is 50 kA (see DS-MCCB-ABS-403c, section 2.1). It complies with IEC 60947-2."
)


def _draft(text: str, **kw) -> Draft:
    return Draft(text=text, model="gemini-test", **kw)


def _code_checks(text, *, category=Category.TECH_SPEC, language="en", evidence=(DS_EVIDENCE,),
                 inquiry=INQUIRY, slots=None, required=()):  # fmt: skip
    draft = _draft(text, slots=slots or {})
    sources = V.build_sources(inquiry, list(evidence), draft)
    values = V.extract_values(text)
    return {
        c.name: c
        for c in (
            V.check_slots(draft, required),
            V.check_values(draft, required, values, sources),
            V.check_specs(values, sources),
            V.check_language(draft, language, sources),
            V.check_banned(draft, category, language),
        )
    }


def _failed(checks) -> set[str]:
    return {name for name, c in checks.items() if not c.passed}


# --- 값 읽기 -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("token", "expected"),
    [
        ("2,515.00", {2515.0}),
        ("2.515,00", {2515.0}),
        ("1,5", {1.5}),
        ("1,000", {1000.0, 1.0}),  # 영어 천 단위 또는 유럽식 소수
        ("25.8", {25.8}),
        ("400", {400.0}),
    ],
)
def test_number_values_reads_both_separators(token, expected):
    assert V.number_values(token) == expected


def test_extract_values_kinds():
    text = (
        "Rated current 15, 20, 30 A, 380–480 V, 25 kA / 3 s, 1000kVA, IP54. "
        "Lead time 4 weeks (12 semanas), USD 2,515.00, ship on 2025-11-22, firmware v3.20. "
        "See DS-ACB-AS-2000 and FAQ-LV_BREAKER. Complies with IEC 60947-2, CE marked."
    )
    found = {(v.kind, v.text) for v in V.extract_values(text)}

    assert {("spec", "15 A"), ("spec", "20 A"), ("spec", "30 A")} <= found  # 목록에 단위 붙이기
    assert {("spec", "380 V"), ("spec", "480 V"), ("spec", "1000 kVA")} <= found
    assert ("spec", "25 s") not in found  # "25 kA / 3 s": 제 단위가 있는 수에는 안 붙인다
    assert {("duration", "4 weeks"), ("duration", "12 semanas")} <= found
    assert {("money", "USD 2,515.00"), ("date", "2025-11-22"), ("number", "3.20")} <= found
    assert {("id", "DS-ACB-AS-2000"), ("id", "FAQ-LV_BREAKER"), ("ip", "IP54")} <= found
    assert {("standard", "IEC 60947-2"), ("mark", "CE")} <= found


def test_ids_are_not_hyphenated_words():
    found = {v.text for v in V.extract_values("Anbei das KC-Zertifikat, CE-marked, Wi-Fi.")}
    assert not {"KC-Zertifikat", "CE-marked", "Wi-Fi"} & found


def test_spanish_en_is_not_a_standard():
    assert not [v for v in V.extract_values("Se enviará en 2026.") if v.kind == "standard"]


def test_split_sentences_keeps_decimals_and_abbreviations():
    text = "Version 3.20 is the latest, e.g. for v1.4 units. Please update.\n- Step two。次へ"
    assert V.split_sentences(text) == [
        "Version 3.20 is the latest, e.g. for v1.4 units.",
        "Please update.",
        "Step two。",
        "次へ",
    ]


# --- 1~5 코드 점검: 맞는 답변은 통과 ---------------------------------------------------------


def test_good_answer_passes_all_code_checks():
    assert _failed(_code_checks(GOOD)) == set()


def test_reformatted_values_still_match():
    # 공백·표기 차이, SI 접두어, 제품명 속 숫자, 고객이 말한 값
    text = (
        "MCCB 400AF: Icu 50kA at 415V, rated voltage up to 0.69 kV, frame 400AF. "
        "For your 415 V panel this rating applies."
    )
    assert _failed(_code_checks(text)) == set()


def test_customer_stated_values_are_allowed():
    inquiry = "We run a 1250 A busbar with IP65 enclosures. Is the MCCB 400AF OK?"
    text = "For your 1250 A busbar in IP65 enclosures, the MCCB 400AF is rated 50 kA at 415 V."
    assert _failed(_code_checks(text, inquiry=inquiry)) == set()


def test_reference_table_values_count_as_sources():
    # 기준표(product_master)의 보증·납기·정가는 코드가 조회한 사실이다
    text = "MCCB 400AF has an 18 months warranty and a standard lead time of 5 weeks."
    assert _failed(_code_checks(text, category=Category.ORDER_LEAD)) == set()


# --- 1~5 코드 점검: 일부러 틀린 답변을 잡는다 (완료 기준: 10개 이상) ----------------------------


WRONG_ANSWERS = [
    ("값을 바꿈", GOOD.replace("50 kA", "65 kA"), "specs"),
    ("근거 없는 사양", GOOD + " The rated insulation voltage is 1000 V.", "specs"),
    ("근거 없는 규격", GOOD + " It is also certified to UL 1077.", "specs"),
    ("더 구체적인 다른 부 규격", GOOD.replace("IEC 60947-2", "IEC 60947-4-1"), "specs"),
    ("근거 없는 인증", GOOD + " The breaker is ATEX certified.", "specs"),
    ("근거 없는 보호 등급", GOOD + " The enclosure is IP67.", "specs"),
    ("다른 제품 문서", GOOD.replace("DS-MCCB-ABS-403c", "DS-ACB-AS-2000"), "values"),
    ("지어낸 RMA", GOOD + " RMA RMA-261234 has been opened.", "values"),
    ("지어낸 가격", GOOD + " The unit price is USD 1,937.40.", "values"),
    ("지어낸 납기", GOOD + " Delivery takes 13 weeks.", "values"),
    ("지어낸 날짜", GOOD + " It will ship on 2026-12-03.", "values"),
    ("지어낸 버전", GOOD + " Firmware 9.87 fixes this.", "values"),
    ("지어낸 에러코드", GOOD + " Error E.XY means overload.", "values"),
]


@pytest.mark.parametrize(
    ("label", "text", "check"), WRONG_ANSWERS, ids=[w[0] for w in WRONG_ANSWERS]
)
def test_wrong_answer_is_caught(label, text, check):
    checks = _code_checks(text)
    assert not checks[check].passed, label
    assert checks[check].reason  # 재작성 때 그대로 쓰는 사람이 읽는 사유


def test_reason_names_the_invented_value():
    reason = _code_checks(GOOD + " Delivery takes 13 weeks.")["values"].reason
    assert "13 weeks" in reason and "기간" in reason


def test_required_slots_must_be_filled_and_used():
    slots = {"unit_price": "USD 25.15", "quote_validity": ""}
    checks = _code_checks(
        "Unit price USD 25.15.", category=Category.QUOTE, slots=slots,
        required=("unit_price", "quote_validity"),
    )  # fmt: skip
    assert "quote_validity" in checks["slots"].reason

    changed = _code_checks(
        "Unit price USD 26.00.", category=Category.QUOTE,
        slots={"unit_price": "USD 25.15"}, required=("unit_price",),
    )  # fmt: skip
    assert not changed["values"].passed and "unit_price" in changed["values"].reason


# --- 4 language ----------------------------------------------------------------------------


def test_wrong_language_is_caught():
    checks = _code_checks(GOOD, language="es")
    assert not checks["language"].passed and "(es)" in checks["language"].reason


def test_copied_english_terms_in_customer_language_pass():
    # 근거의 영어 속성명·제품명을 그대로 옮겨도 고객 언어 답변이다 (실제 회신 형태)
    es = (
        "El valor de Ultimate breaking capacity Icu at AC 415 V de MCCB 400AF es 50 kA. "
        "Referencia: DS-MCCB-ABS-403c, sección 2.1."
    )
    th = (
        "Ultimate breaking capacity Icu at AC 415 V ของ MCCB 400AF คือ 50 kA ค่ะ "
        "อ้างอิง: DS-MCCB-ABS-403c"
    )
    zh = (
        "MCCB 400AF的Ultimate breaking capacity Icu at AC 415 V为50 kA。"
        "参考：DS-MCCB-ABS-403c，第2.1节。"
    )
    assert _code_checks(es, language="es")["language"].passed
    assert _code_checks(th, language="th")["language"].passed
    assert _code_checks(zh, language="zh")["language"].passed


def test_one_english_sentence_in_spanish_reply_is_caught():
    text = (
        "Gracias por su consulta. La capacidad de corte del interruptor es de 50 kA según "
        "DS-MCCB-ABS-403c. Le recomendamos revisar también la coordinación con los demás equipos "
        "de su instalación antes de la puesta en marcha. "
        "Please contact our sales team for the price and we will get back to you soon."
    )
    reason = _code_checks(text, language="es")["language"].reason
    assert "4번 문장(en)" in reason


def test_script_mismatch_is_caught():
    assert not _code_checks("このブレーカーの遮断容量は50 kAです。", language="zh")[
        "language"
    ].passed
    assert not _code_checks("차단 용량은 50 kA입니다.", language="ja")["language"].passed
    assert _code_checks("차단 용량은 50 kA입니다.", language="ko")["language"].passed


# --- 5 banned ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("category", "language", "text"),
    [
        (Category.DEFECT, "en", "The root cause is a failed cooling fan."),
        (Category.DEFECT, "en", "Diagnosis: IGBT module damaged."),
        (Category.INSTALL, "en", "The issue was caused by a loose terminal."),
        (Category.DEFECT, "es", "La causa raíz es un ventilador averiado."),
        (Category.DEFECT, "ko", "원인은 냉각팬 고장입니다."),
        (Category.FW_UPDATE, "zh", "根本原因是固件版本过旧。"),
        (Category.RETURN, "en", "Your return has been approved under RMA RMA-260057."),
        (Category.RETURN, "en", "Unfortunately we cannot accept your return."),
        (Category.WARRANTY, "en", "Our inspection found water ingress, which is not covered."),
        (Category.WARRANTY, "de", "Ihr Anspruch wurde im Rahmen der Garantie genehmigt."),
        (Category.WARRANTY, "ja", "保証修理を承認いたしました。"),
        (Category.RETURN, "ko", "반품이 승인되었습니다."),
        (Category.RETURN, "th", "อนุมัติการคืนสินค้าภายใต้ RMA RMA-260853 แล้ว"),
    ],
)
def test_banned_expressions_are_caught(category, language, text):
    found = V.find_banned(text, category, language)
    assert found and found[0][0] == 1


@pytest.mark.parametrize(
    ("category", "language", "text"),
    [
        (Category.DEFECT, "en", "Possible causes: a failed cooling fan or a clogged air filter."),
        (
            Category.DEFECT,
            "en",
            "The root cause is likely a loose terminal; please check it first.",
        ),
        (Category.DEFECT, "ko", "원인은 냉각팬 고장일 가능성이 있습니다."),
        (Category.RETURN, "en", "Once approved, we will issue an RMA number."),
        (Category.RETURN, "en", "Returns are accepted within 30 days in original packaging."),
        (Category.RETURN, "en", "After 30 days: not accepted. Units without RMA are refused."),
        (Category.WARRANTY, "en", "The unit is within the 18 months warranty period."),
        (Category.WARRANTY, "ko", "보증 승인 여부는 담당 부서가 검토 후 안내드립니다."),
        (Category.RETURN, "es", "Se requiere el número de factura para tramitar la devolución."),
        (Category.TECH_SPEC, "en", "The root cause is not relevant to a spec question."),  # 정보형
    ],
)
def test_hedged_conditional_and_policy_sentences_pass(category, language, text):
    assert V.find_banned(text, category, language) == []


def test_banned_reason_points_to_sentence_and_fix():
    reason = V.check_banned(
        _draft("Thanks for the logs. The root cause is a failed fan."), Category.DEFECT
    ).reason
    assert "2번 문장" in reason and "원인 후보" in reason


# --- 6 grounding ---------------------------------------------------------------------------


class ScriptedJudge:
    """task·프롬프트를 보고 정해 둔 답을 주는 판단 모델 대역."""

    name = "judge-test"

    def __init__(self, overall=("yes", 0.9), sentence=None, fail=False):
        self.overall, self.sentence, self.fail = overall, sentence or {}, fail
        self.prompts: list[str] = []
        self.lock = threading.Lock()

    def judge(self, prompt, options):
        with self.lock:
            self.prompts.append(prompt)
        if self.fail:
            raise TimeoutError("judge timeout")
        if "Sentence " in prompt:
            n = int(prompt.split("\n\nSentence ")[1].split(":")[0])
            answer, confidence = self.sentence.get(n, ("yes", 0.9))
        else:
            answer, confidence = self.overall
        return Judgement(answer, confidence, self.name)


def _llm(judge) -> LLMRouter:
    return LLMRouter(Settings(_env_file=None), gemini_judge=judge)


def test_grounding_passes_with_one_call_when_all_supported():
    judge = ScriptedJudge()
    result = V.check_grounding(_draft(GOOD), INQUIRY, [DS_EVIDENCE], _llm(judge))

    assert result.passed and len(judge.prompts) == 1
    prompt = judge.prompts[0]
    assert "DS-MCCB-ABS-403c#2.1" in prompt and "50 kA" in prompt and INQUIRY in prompt


def test_grounding_names_unsupported_sentences():
    judge = ScriptedJudge(overall=("no", 0.9), sentence={2: ("no", 0.95)})
    text = GOOD + " It also supports Modbus TCP."
    result = V.check_grounding(_draft(text), INQUIRY, [DS_EVIDENCE], _llm(judge))

    assert not result.passed
    assert result.reason.startswith("2번 문장 근거 없음")  # 1-based, "It complies…" 는 3번
    assert len(judge.prompts) == 1 + len(V.split_sentences(text))
    sentence_prompts = [p for p in judge.prompts if "\n\nSentence " in p]
    # 문장마다 근거·문의를 같이 보여 준다
    assert all(
        "50 kA" in p and "DS-MCCB-ABS-403c#2.1" in p and INQUIRY in p for p in sentence_prompts
    )


def test_grounding_sentence_calls_keep_ticket_trace():
    from cs_agent.llm import tracing

    seen = []

    class TraceJudge(ScriptedJudge):
        def judge(self, prompt, options):
            seen.append(tracing._ticket_id.get())
            return super().judge(prompt, options)

    judge = TraceJudge(overall=("no", 0.9))
    with tracing.ticket_scope("T-TRACE"):
        V.check_grounding(_draft(GOOD), INQUIRY, [DS_EVIDENCE], _llm(judge))
    assert len(seen) > 1 and set(seen) == {"T-TRACE"}


def test_grounding_treats_low_confidence_as_uncertain():
    judge = ScriptedJudge(overall=("yes", 0.3), sentence={1: ("yes", 0.2)})
    result = V.check_grounding(_draft(GOOD), INQUIRY, [DS_EVIDENCE], _llm(judge))

    assert not result.passed and "1번 문장 근거 확인 불확실" in result.reason


def test_grounding_overall_no_but_every_sentence_yes_passes():
    judge = ScriptedJudge(overall=("no", 0.6))
    assert V.check_grounding(_draft(GOOD), INQUIRY, [DS_EVIDENCE], _llm(judge)).passed


def test_grounding_error_fails_for_human_review():
    result = V.check_grounding(_draft(GOOD), INQUIRY, [DS_EVIDENCE], _llm(ScriptedJudge(fail=True)))
    assert not result.passed and "TimeoutError" in result.reason


def test_grounding_skipped_when_judge_is_off():
    result = V.check_grounding(
        _draft(GOOD), INQUIRY, [DS_EVIDENCE], LLMRouter(Settings(_env_file=None))
    )
    assert result.passed and "생략" in result.reason


# --- verify(): 순서·생략 ------------------------------------------------------------------------


def test_verify_runs_grounding_only_after_code_checks_pass():
    judge = ScriptedJudge()
    ok = V.verify(_draft(GOOD), Category.TECH_SPEC, (), INQUIRY, "en", [DS_EVIDENCE], _llm(judge))
    assert [c.name for c in ok] == ["slots", "values", "specs", "language", "banned", "grounding"]
    assert all(c.passed for c in ok) and len(judge.prompts) == 1

    judge = ScriptedJudge()
    bad = V.verify(_draft(GOOD + " Delivery takes 13 weeks."), Category.TECH_SPEC, (), INQUIRY,
                   "en", [DS_EVIDENCE], _llm(judge))  # fmt: skip
    assert "grounding" not in [c.name for c in bad] and judge.prompts == []


def test_verify_empty_and_placeholder_drafts():
    llm = LLMRouter(Settings(_env_file=None))
    empty = V.verify(_draft("  "), Category.TECH_SPEC, (), INQUIRY, "en", [], llm)
    assert not empty[-1].passed and empty[-1].reason == "답변이 비어 있음"

    placeholder = Draft(text="[LLM 꺼짐] prompt…", model=FakeWriter.name)
    checks = V.verify(placeholder, Category.TECH_SPEC, (), INQUIRY, "ko", [], llm)
    assert all(c.passed for c in checks) and "생략" in checks[-1].reason


# --- 실제 데이터 회귀 (data/raw: tickets 실제 회신 + 정답 근거 절) -----------------------------


@pytest.fixture(scope="module")
def corpus():
    from cs_agent.pipeline.chunking import iter_doc_chunks

    path = REPO_ROOT / "data" / "raw" / "tickets.csv"
    if not path.exists():
        pytest.skip("data/raw/tickets.csv 없음")
    with path.open(encoding="utf-8-sig") as f:
        rows = [r for r in csv.DictReader(f) if r["final_reply"].strip()]
    chunks = {}
    for c in iter_doc_chunks(REPO_ROOT / "data" / "raw" / "docs"):
        chunks[f"{c.doc_id}#{c.section}"] = c
        chunks.setdefault(c.doc_id, c)
    return rows, chunks


def _evidence(row, chunks):
    c = chunks.get(f"{row['reference_doc_id']}#{row['reference_section']}") or chunks.get(
        row["reference_doc_id"]
    )
    if not c:
        return []
    meta = {k: c.metadata.get(k, "") for k in ("doc_type", "product_code", "family")}
    return [Evidence(source="docs", doc_id=c.doc_id, section=c.section, text=c.text, metadata=meta)]


DOC_BASED = ("TECH_SPEC", "COMPLIANCE", "MANUAL", "FW_UPDATE")


def test_real_doc_based_replies_pass_code_checks(corpus):
    """근거 문서만으로 쓴 실제 회신(1,571건)은 코드 점검을 통과해야 한다 (오탐 0)."""
    rows, chunks = corpus
    failures = []
    for row in (r for r in rows if r["category_code"] in DOC_BASED):
        checks = _code_checks(
            row["final_reply"], category=Category(row["category_code"]), language=row["language"],
            evidence=_evidence(row, chunks),
            inquiry=f"{row['inquiry_subject']}\n{row['inquiry_body']}",
        )  # fmt: skip
        if _failed(checks):
            failures.append((row["ticket_id"], {k: checks[k].reason for k in _failed(checks)}))
    assert failures == []


def test_real_replies_language_false_positives_are_rare(corpus):
    rows, chunks = corpus
    wrong = 0
    for row in rows:
        source = "\n".join(
            [e.text for e in _evidence(row, chunks)]
            + [row["inquiry_subject"], row["inquiry_body"], row["product_name"]]
        )
        wrong += bool(V.detect_mismatch(row["final_reply"], row["language"], source))
    assert wrong / len(rows) <= 0.002  # 측정: 1/3,635


def test_real_replies_in_another_language_are_caught(corpus):
    rows, chunks = corpus
    rng = random.Random(1)
    languages = sorted({r["language"] for r in rows})
    by_language = {lang: [r for r in rows if r["language"] == lang] for lang in languages}
    caught = 0
    for row in rows:
        other = rng.choice(
            by_language[rng.choice([lang for lang in languages if lang != row["language"]])]
        )
        source = "\n".join([e.text for e in _evidence(other, chunks)] + [other["inquiry_body"]])
        caught += bool(V.detect_mismatch(other["final_reply"], row["language"], source))
    assert caught / len(rows) >= 0.99  # 측정: 99.4%


def test_real_decisions_are_caught_and_policy_text_is_not(corpus):
    rows, chunks = corpus
    # 사람이 판정한 실제 회신: 반품 승인·거절, 진단 단정
    for category, minimum in (("RETURN", 0.9), ("DEFECT", 0.8)):
        replies = [r for r in rows if r["category_code"] == category]
        hit = sum(
            bool(V.find_banned(r["final_reply"], Category(category), r["language"]))
            for r in replies
        )
        assert hit / len(replies) >= minimum, category
    # 정책 조항·문제 해결 가이드의 "Possible cause" 는 판정이 아니다
    for chunk in {id(c): c for c in chunks.values()}.values():
        doc_type = chunk.metadata.get("doc_type")
        category = {"POL": Category.RETURN, "TG": Category.DEFECT, "IG": Category.INSTALL}.get(
            doc_type
        )
        if category:
            assert V.find_banned(chunk.text, category, "en") == [], chunk.doc_id
