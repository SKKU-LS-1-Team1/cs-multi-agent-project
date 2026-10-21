import csv

import pytest

from cs_agent.agents.info_request import (
    FALLBACK_ITEM,
    build_prompt,
    check_request,
    count_items,
    item_labels,
    template_request,
    write_info_request,
)
from cs_agent.config import Settings, get_settings
from cs_agent.llm.clients import Completion
from cs_agent.llm.router import LLMRouter
from cs_agent.rules.tables import load_tables

LABELS = load_tables().field_labels


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


def live(writer) -> LLMRouter:
    return LLMRouter(Settings(_env_file=None, llm_provider="live"), writer=writer)


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
        "Serial number (nameplate)",
        "Photos of product and nameplate",
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
    assert "1. Incoterms and delivery destination\n2. Quantity" in prompt
    assert "numbered list 1. to 2." in prompt
    assert prompt.endswith("\n" + "x" * 2000)  # 문의 원문은 앞 2,000자만


def test_without_llm_returns_english_template_with_all_items() -> None:
    text = write_info_request(
        ["product_model", "serial_no"], "es", "inquiry", LLMRouter(Settings(_env_file=None))
    )
    assert count_items(text) == 2
    assert "1. Product model / ordering code\n2. Serial number (nameplate)" in text


def test_live_writes_in_customer_language() -> None:
    writer = ScriptedWriter(SPANISH_OK)

    text = write_info_request(["product_model", "serial_no"], "es", "¿Dimensiones?", live(writer))

    assert text == SPANISH_OK
    assert len(writer.prompts) == 1 and "¿Dimensiones?" in writer.prompts[0]


def test_retries_once_with_reason_then_accepts() -> None:
    missing_one = SPANISH_OK.replace("2. Número de serie (placa de características)\n", "")
    writer = ScriptedWriter(missing_one, SPANISH_OK)

    text = write_info_request(["product_model", "serial_no"], "es", "q", live(writer))

    assert text == SPANISH_OK
    assert "must have exactly 2" in writer.prompts[1]


def test_falls_back_to_template_when_still_wrong_or_llm_fails() -> None:
    items = ["product_model", "serial_no"]
    english = template_request(item_labels(items, LABELS))

    still_wrong = ScriptedWriter("1. solo uno", "1. solo uno")
    assert write_info_request(items, "es", "q", live(still_wrong)) == english
    assert len(still_wrong.prompts) == 2

    down = ScriptedWriter(TimeoutError("gemini down"))
    assert write_info_request(items, "es", "q", live(down)) == english


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
