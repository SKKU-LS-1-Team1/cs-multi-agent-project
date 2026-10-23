import csv

import pytest

from cs_agent.agents.info_request import (
    ATTEMPTS,
    FALLBACK_ITEM,
    LocalizationError,
    build_prompt,
    check_request,
    count_items,
    in_language,
    item_labels,
    localize_request,
    template_request,
    write_info_request,
)
from cs_agent.cache.store import MemoryKV
from cs_agent.config import Settings, get_settings
from cs_agent.llm.clients import Completion
from cs_agent.llm.router import LLMRouter
from cs_agent.rules.tables import load_tables

_TABLES = load_tables()
# 요청문이 실제로 쓰는 라벨: 쉬운 이름(info_request_labels) 우선, 없으면 codebook 라벨
LABELS = {**_TABLES.field_labels, **_TABLES.request_labels}


class ScriptedWriter:
    """정해 둔 답을 차례로 돌려준다. 예외 객체면 던진다."""

    name = "gemini-writer"

    def __init__(self, *outputs):
        self.outputs = list(outputs)
        self.prompts: list[str] = []

    def write(self, prompt):
        self.prompts.append(prompt)
        out = self.outputs.pop(0)
        if isinstance(out, Exception):
            raise out
        return Completion(out, self.name)


def live(writer, kv=None) -> LLMRouter:
    return LLMRouter(Settings(_env_file=None, llm_provider="live"), writer=writer, kv=kv)


SPANISH_OK = """Estimado cliente:

Gracias por contactarnos. Para continuar con su consulta, le pedimos que nos envíe en una sola
respuesta la siguiente información:

1. Modelo del producto / código de pedido
2. Número de serie (placa de características)

Quedamos atentos a su respuesta.

Atentamente,
Equipo de atención al cliente"""


# --- 항목 라벨 ---------------------------------------------------------------------------------


def test_every_field_has_a_customer_label() -> None:
    """required_info.csv 와 valid 문의의 missing_info 항목은 모두 라벨이 있다."""
    tables = get_settings().ref_dir
    fields = set()
    with (tables / "required_info.csv").open(encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            fields |= {x for x in f"{r['required_fields']};{r['blocking_fields']}".split(";") if x}
    assert fields and fields <= set(LABELS)


def test_item_labels_dedupes_and_falls_back() -> None:
    assert item_labels(["serial_no", "serial_no", " ", "photos"], LABELS) == [
        "Serial number printed on the product's nameplate label",
        "Photos of the product and of its nameplate label",
    ]
    assert item_labels(["unknown_field"], LABELS) == ["unknown field"]
    assert item_labels([], LABELS) == [FALLBACK_ITEM]


# --- 점검 --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text, n",
    [
        ("1. a\n2. b", 2),
        ("1) a\n 2) b\n3) c", 3),
        ("**1.** a\n**2.** b", 2),
        ("１．型番\n２．シリアル番号", 2),  # 전각 숫자
        ("1、型号\n2、序列号", 2),
        ("Model 2. version only in text", 0),
    ],
)
def test_count_items(text, n) -> None:
    assert count_items(text) == n


def test_check_request_finds_missing_items_and_wrong_language() -> None:
    items = item_labels(["product_model", "serial_no"], LABELS)

    assert check_request(SPANISH_OK, items, "es") == []
    one_item = SPANISH_OK.replace("2. Número de serie (placa de características)\n", "")
    assert "must have exactly 2" in check_request(one_item, items, "es")[0]
    english = template_request(items)
    assert any("not Thai" in p for p in check_request(english, items, "th"))
    assert check_request("  ", items, "es") == ["empty message"]


@pytest.mark.parametrize(
    "language, text",
    [
        (
            "th",
            "เรียนลูกค้า\n\nขอบคุณที่ติดต่อเรา กรุณาส่งข้อมูลต่อไปนี้ในการตอบกลับครั้งเดียว\n\n"
            "1. รุ่นผลิตภัณฑ์ / รหัสสั่งซื้อ\n2. หมายเลขซีเรียล (แผ่นป้าย)\n\n"
            "ขอแสดงความนับถือ\nทีมบริการลูกค้า",
        ),
        (
            "zh",
            "尊敬的客户：\n\n感谢您的来信。请在一次回复中提供以下信息：\n\n"
            "1. 产品型号 / 订货号\n2. 序列号（铭牌）\n\n此致\n客户服务团队",
        ),
        (
            "ar",
            "عزيزي العميل،\n\nشكرًا لتواصلك معنا. يرجى إرسال المعلومات التالية في رد واحد:\n\n"
            "1. طراز المنتج / رمز الطلب\n2. الرقم التسلسلي (لوحة البيانات)\n\n"
            "مع أطيب التحيات،\nفريق خدمة العملاء",
        ),
    ],
)
def test_check_request_accepts_non_latin_languages(language, text) -> None:
    items = item_labels(["product_model", "serial_no"], LABELS)
    assert check_request(text, items, language) == []


# --- 작성 --------------------------------------------------------------------------------------


def test_prompt_lists_every_item_in_order_with_language() -> None:
    items = item_labels(["incoterms", "quantity"], LABELS)

    prompt = build_prompt(items, "es", "x" * 5000)

    assert "in Spanish" in prompt
    assert f"1. {LABELS['incoterms']}\n2. {LABELS['quantity']}" in prompt
    assert "numbered list 1. to 2." in prompt
    assert prompt.endswith("\n" + "x" * 2000)  # 문의 원문은 앞 2,000자만


def test_without_llm_returns_english_template_with_all_items() -> None:
    text = write_info_request(
        ["product_model", "serial_no"], "es", "inquiry", LLMRouter(Settings(_env_file=None))
    )
    assert count_items(text) == 2
    assert f"1. {LABELS['product_model']}\n2. {LABELS['serial_no']}" in text


@pytest.mark.parametrize("language", ["en", "es", "fr", "ar", "zh", "ja", "ko"])
def test_live_writes_english_for_staff_review(language) -> None:
    writer = ScriptedWriter(ENGLISH)

    text = write_info_request(
        ["product_model", "serial_no"], language, "¿Dimensiones?", live(writer)
    )

    assert text == ENGLISH
    assert len(writer.prompts) == 1 and "¿Dimensiones?" in writer.prompts[0]
    assert "in English" in writer.prompts[0]


def test_non_english_review_draft_is_rejected_even_for_same_language_customer() -> None:
    writer = ScriptedWriter(SPANISH_OK, ENGLISH)
    text = write_info_request(["product_model", "serial_no"], "es", "consulta", live(writer))
    assert text == ENGLISH
    assert len(writer.prompts) == 2


def test_retries_once_with_reason_then_accepts() -> None:
    missing_one = template_request(item_labels(["product_model"], LABELS))
    writer = ScriptedWriter(missing_one, ENGLISH)

    text = write_info_request(["product_model", "serial_no"], "es", "q", live(writer))

    assert text == ENGLISH
    assert "must have exactly 2" in writer.prompts[1]


def test_draft_tries_three_times_then_english_template_for_review() -> None:
    """초안은 3번까지 다시 쓰고, 그래도 안 되면 상담원 화면용 영어 틀 문장 (보낼 때 번역된다)."""
    items = ["product_model", "serial_no"]
    english = template_request(item_labels(items, LABELS))

    third_time = ScriptedWriter("1. solo uno", TimeoutError("busy"), ENGLISH)
    assert write_info_request(items, "es", "q", live(third_time)) == ENGLISH
    assert len(third_time.prompts) == ATTEMPTS == 3
    assert "the call failed (TimeoutError)" in third_time.prompts[2]  # 호출 오류도 1번으로 센다

    never = ScriptedWriter("1. solo uno", "1. solo uno", "1. solo uno")
    assert write_info_request(items, "es", "q", live(never)) == english
    assert len(never.prompts) == 3


def test_valid_tickets_with_missing_info_get_every_item() -> None:
    """완료 기준 1: valid 중 missing_info 가 있는 건 → 요청문(틀 문장)에 빠진 항목이 전부 들어감."""
    path = get_settings().raw_data_dir / "tickets.csv"
    if not path.exists():
        pytest.skip("data/raw/tickets.csv 없음")
    router = LLMRouter(Settings(_env_file=None))
    checked = 0
    with path.open(encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            if r["data_split"] != "valid" or not r["missing_info"]:
                continue
            missing = r["missing_info"].split(";")
            text = write_info_request(missing, r["language"], r["inquiry_body"], router)
            assert count_items(text) == len(set(missing))
            assert all(LABELS[m] in text for m in missing)
            checked += 1
    assert checked > 0


# --- 보낼 때 고객 언어로 -------------------------------------------------------------------------

ENGLISH = template_request(item_labels(["product_model", "serial_no"], LABELS))


def test_localize_translates_english_request_into_customer_language() -> None:
    writer = ScriptedWriter(SPANISH_OK)

    assert localize_request(ENGLISH, "es", live(writer)) == SPANISH_OK
    assert "into Spanish" in writer.prompts[0] and "exactly 2 items" in writer.prompts[0]


def test_localize_skips_only_when_already_customer_language() -> None:
    writer = ScriptedWriter()
    assert localize_request(SPANISH_OK, "es", live(writer)) == SPANISH_OK
    assert localize_request(ENGLISH, "en", live(writer)) == ENGLISH
    assert writer.prompts == []  # 부르지 않았다


def test_localize_never_returns_english_for_non_english_customer() -> None:
    """번역 모델이 꺼져 있거나 3번 다 실패하면 LocalizationError — 영어 원문을 돌려주지 않는다."""
    with pytest.raises(LocalizationError, match="꺼져"):
        localize_request(ENGLISH, "es", LLMRouter(Settings(_env_file=None)))

    still_english = ScriptedWriter(ENGLISH, ENGLISH, ENGLISH)
    with pytest.raises(LocalizationError, match="3번 실패"):
        localize_request(ENGLISH, "es", live(still_english))
    assert len(still_english.prompts) == 3

    down = ScriptedWriter(*(TimeoutError("gemini down") for _ in range(3)))
    with pytest.raises(LocalizationError):
        localize_request(ENGLISH, "es", live(down))

    with pytest.raises(LocalizationError, match="비어"):
        localize_request("  ", "es", live(ScriptedWriter()))


def test_localize_succeeds_on_third_attempt() -> None:
    dropped = SPANISH_OK.replace("2. Número de serie (placa de características)\n", "")
    writer = ScriptedWriter(dropped, TimeoutError("busy"), SPANISH_OK)

    assert localize_request(ENGLISH, "es", live(writer)) == SPANISH_OK
    assert "must have 2" in writer.prompts[1]


def test_rejected_translation_is_evicted_from_cache() -> None:
    """거른 번역이 캐시에 남으면 다시 승인해도 같은 나쁜 답만 받는다 → 캐시에서 지운다."""
    kv = MemoryKV()
    bad = ScriptedWriter(ENGLISH, ENGLISH, ENGLISH)
    with pytest.raises(LocalizationError):
        localize_request(ENGLISH, "es", live(bad, kv))

    good = ScriptedWriter(SPANISH_OK)  # 상담원이 다시 승인 → 같은 프롬프트로 첫 시도
    assert localize_request(ENGLISH, "es", live(good, kv)) == SPANISH_OK
    assert len(good.prompts) == 1  # 캐시가 아니라 모델을 다시 불렀다


@pytest.mark.parametrize("language", ["es", "fr", "de", "it", "pt", "id", "tr", "vi", "pl"])
def test_english_is_rejected_for_latin_languages(language) -> None:
    """영어로 쓴 글은 라틴 문자 고객 언어에서도 걸린다 (초안 점검·번역 점검 모두)."""
    items = item_labels(["product_model", "serial_no"], LABELS)
    assert any("'en'" in p for p in check_request(ENGLISH, items, language))
    writer = ScriptedWriter(ENGLISH, ENGLISH, ENGLISH)
    with pytest.raises(LocalizationError):
        localize_request(ENGLISH, language, live(writer))
    assert len(writer.prompts) == 3  # 번역 안 된 글은 통과시키지 않고 다시 시도했다


@pytest.mark.parametrize(
    "text, language, expected",
    [
        (SPANISH_OK, "es", True),
        (ENGLISH, "en", True),
        (ENGLISH, "es", False),
        ("Bitte senden Sie uns die Seriennummer und Fotos des Typenschilds.", "de", True),
        ("Hi, send model pls", "de", False),  # 짧아 판단이 안 됨 → 확인 안 된 것
        ("OK", "es", False),
        ("1. TRF-OIL-1000 S/N 12345", "es", False),  # ID·숫자뿐
        ("Por favor envíe el número de serie y las fotos.", "de", False),
        ("Please send the nameplate photos and serial number.", "xx", False),  # 모르는 언어
    ],
)
def test_in_language_requires_positive_confirmation(text, language, expected) -> None:
    assert in_language(text, language) is expected


@pytest.mark.parametrize(
    "language, short_english",
    [("de", "Hi, send model pls"), ("es", "OK"), ("fr", "Send S/N")],
)
def test_short_english_is_never_sent_as_is(language, short_english) -> None:
    """판단이 안 되는 짧은 영어도 '이미 고객 언어'로 넘기지 않고 번역 → 확인 안 되면 보류."""
    writer = ScriptedWriter(short_english, short_english, short_english)
    with pytest.raises(LocalizationError):
        localize_request(short_english, language, live(writer))
    assert len(writer.prompts) == 3


def test_request_uses_plain_labels_for_customers() -> None:
    from cs_agent.agents.info_request import _field_labels

    labels = _field_labels()
    assert labels == LABELS
    items = item_labels(["serial_no", "incoterms", "unknown_field"], labels)

    assert items[0] == "Serial number printed on the product's nameplate label"
    assert items[1].startswith("Delivery terms and delivery address")
    assert items[2] == "unknown field"
    text = template_request(items)
    assert all(f"{i}. {item}" in text for i, item in enumerate(items, 1))
