import pytest

from cs_agent.chatbot.navigation import Navigation, decide
from cs_agent.domain import Category
from cs_agent.rules.tables import load_tables
from cs_agent.schemas import Classification, Extraction

TABLES = load_tables()


def _classified(category: Category, confidence: float = 0.9) -> Classification:
    return Classification(category=category, confidence=confidence)


def _extracted(code: str | None = None, family: str | None = None, **kw: str) -> Extraction:
    return Extraction(product_code=code, product_family=family, **kw)


# 기획서 5.4 표의 예 8개


def test_product_only_opens_info_tab() -> None:
    # "iS7 75kW 알려줘"
    nav = decide(_extracted("INV-LSLV0750-iS7"), None, TABLES)

    assert nav == Navigation(
        product_code="INV-LSLV0750-iS7", tab="info", anchor=None, rule_id="NAV-01"
    )


def test_family_only_offers_product_buttons() -> None:
    # "인버터 문의할게요"
    nav = decide(_extracted(family="DRIVE"), None, TABLES)

    assert nav.product_code is None
    assert (nav.tab, nav.anchor, nav.rule_id) == ("tree", "DRIVE", "NAV-02")
    assert set(nav.candidates) == {"INV-LSLV0075-S100", "INV-LSLV0220-H100", "INV-LSLV0750-iS7"}


def test_tech_spec_highlights_spec_row() -> None:
    # "ACB 2000A 차단 용량은?"
    nav = decide(_extracted("ACB-AS-2000"), _classified(Category.TECH_SPEC), TABLES)

    assert (nav.product_code, nav.tab, nav.anchor, nav.rule_id) == (
        "ACB-AS-2000",
        "info",
        "spec_row",
        "NAV-03",
    )


def test_install_opens_install_section() -> None:
    # "MCCB 배선 방법"
    nav = decide(_extracted("MCCB-ABS-103c"), _classified(Category.INSTALL), TABLES)

    assert (nav.tab, nav.anchor, nav.rule_id) == ("install", "section", "NAV-05")


def test_defect_highlights_extracted_error_code() -> None:
    # "S100 가속 중 E.OC"
    extraction = _extracted("INV-LSLV0075-S100", error_code="E.OC")
    nav = decide(extraction, _classified(Category.DEFECT), TABLES)

    assert (nav.product_code, nav.tab, nav.anchor, nav.rule_id) == (
        "INV-LSLV0075-S100",
        "faults",
        "E.OC",
        "NAV-06",
    )


def test_firmware_opens_latest_version() -> None:
    # "XGI 최신 펌웨어?"
    nav = decide(_extracted("PLC-XGI-CPUU"), _classified(Category.FW_UPDATE), TABLES)

    assert (nav.tab, nav.anchor, nav.rule_id) == ("firmware", "latest", "NAV-07")


def test_manual_opens_document_library() -> None:
    # "UPS 설치 매뉴얼 주세요"
    nav = decide(_extracted("UPS-LSU-10K"), _classified(Category.MANUAL), TABLES)

    assert (nav.tab, nav.anchor, nav.rule_id) == ("docs", "doc_id", "NAV-08")


def test_quote_shows_lead_time() -> None:
    # "PCS 100kW 20대 견적"
    nav = decide(_extracted("ESS-PCS-100kW"), _classified(Category.QUOTE), TABLES)

    assert (nav.product_code, nav.tab, nav.anchor, nav.rule_id) == (
        "ESS-PCS-100kW",
        "info",
        "lead_time",
        "NAV-09",
    )


# 규칙표 전체와 경계


@pytest.mark.parametrize("category", list(Category))
def test_every_category_has_a_rule(category: Category) -> None:
    nav = decide(_extracted("ACB-AS-2000"), _classified(category), TABLES)

    assert nav.rule_id == TABLES.navigation[str(category)]["nav_rule_id"]
    assert nav.tab == TABLES.navigation[str(category)]["tab"]


def test_nothing_known_means_no_move() -> None:
    assert decide(_extracted(), None, TABLES) == Navigation()
    assert decide(_extracted(), _classified(Category.DEFECT), TABLES) == Navigation()


def test_unknown_product_with_family_asks_even_when_category_is_known() -> None:
    nav = decide(_extracted(family="DRIVE"), _classified(Category.DEFECT), TABLES)

    assert nav.rule_id == "NAV-02"
    assert nav.product_code is None


def test_family_is_taken_from_product_when_only_code_is_known() -> None:
    # 제품을 알면 제품군은 따로 필요 없다 (FAMILY_ONLY 로 가지 않는다)
    nav = decide(_extracted("INV-LSLV0075-S100", family="DRIVE"), None, TABLES)

    assert nav.rule_id == "NAV-01"
    assert nav.candidates == []


def test_product_code_missing_from_master_is_treated_as_unknown() -> None:
    assert decide(_extracted("NOPE-123"), _classified(Category.DEFECT), TABLES) == Navigation()
    nav = decide(_extracted("NOPE-123", family="DRIVE"), None, TABLES)
    assert nav.rule_id == "NAV-02"


def test_low_confidence_falls_back_to_product_only() -> None:
    extraction = _extracted("ACB-AS-2000")

    nav = decide(extraction, _classified(Category.TECH_SPEC, confidence=0.49), TABLES)

    assert (nav.tab, nav.anchor, nav.rule_id) == ("info", None, "NAV-01")


def test_confidence_equal_to_threshold_counts_as_confident() -> None:
    nav = decide(_extracted("ACB-AS-2000"), _classified(Category.TECH_SPEC, confidence=0.5), TABLES)

    assert nav.rule_id == "NAV-03"


def test_threshold_is_a_parameter() -> None:
    classification = _classified(Category.TECH_SPEC, confidence=0.6)

    strict = decide(_extracted("ACB-AS-2000"), classification, TABLES, min_confidence=0.7)

    assert strict.rule_id == "NAV-01"


def test_defect_without_error_code_has_no_anchor() -> None:
    nav = decide(_extracted("INV-LSLV0075-S100"), _classified(Category.DEFECT), TABLES)

    assert (nav.tab, nav.anchor, nav.rule_id) == ("faults", None, "NAV-06")


def test_same_input_always_opens_same_place() -> None:
    extraction = _extracted("INV-LSLV0075-S100", error_code="E.OC")
    classification = _classified(Category.DEFECT)

    assert decide(extraction, classification, TABLES) == decide(extraction, classification, TABLES)


def test_default_tables_are_loaded_when_omitted() -> None:
    assert decide(_extracted("ACB-AS-2000"), None).rule_id == "NAV-01"
