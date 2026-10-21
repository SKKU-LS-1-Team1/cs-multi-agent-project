import pytest
from fastapi.testclient import TestClient

from cs_agent.config import Settings
from cs_agent.llm.router import LLMRouter
from cs_agent.main import create_app
from cs_agent.services.catalog import TAB_ORDER, get_catalog

CATALOG = get_catalog()
PRODUCTS = list(CATALOG.tables.products)
S100 = "INV-LSLV0075-S100"


@pytest.fixture(scope="module")
def client():
    app = create_app(
        llm=LLMRouter(Settings(_env_file=None)), storage="memory", retrievers=(None, None)
    )
    with TestClient(app) as c:
        yield c


# 트리


def test_tree_has_3_divisions_11_families_23_products(client) -> None:
    tree = client.get("/api/products/tree").json()

    assert [d["label"] for d in tree] == ["전력", "자동화", "에너지"]
    families = [f for d in tree for f in d["families"]]
    assert len(families) == 11
    codes = [p["code"] for f in families for p in f["products"]]
    assert sorted(codes) == sorted(PRODUCTS)
    drive = next(f for f in families if f["family"] == "DRIVE")
    assert drive["label"] == "Variable frequency drives"
    assert {"code": S100, "name": "LSLV S100 7.5kW VFD"} in drive["products"]


# 상세


@pytest.mark.parametrize("code", PRODUCTS)
def test_every_product_has_detail_with_content_for_each_tab(client, code) -> None:
    res = client.get(f"/api/products/{code}")

    assert res.status_code == 200
    detail = res.json()
    assert detail["code"] == code and detail["name"]
    assert detail["tabs"][:3] == ["info", "install", "faults"]  # 모든 제품에 있는 탭
    assert all(detail[tab] for tab in detail["tabs"])  # 탭이 있으면 내용도 있다
    assert all(not detail[tab] for tab in set(TAB_ORDER) - set(detail["tabs"]))
    assert detail["info"]["specs"]
    assert all(f["section"] for f in detail["faults"])  # 고장마다 고장 가이드 절이 있다
    assert "list_price_usd" not in str(detail)  # 정가는 내보내지 않는다


def test_firmware_tab_only_for_products_with_firmware() -> None:
    for code in PRODUCTS:
        has_firmware = CATALOG.master[code]["has_firmware"] == "Y"
        assert ("firmware" in CATALOG.detail(code)["tabs"]) == has_firmware, code


def test_s100_detail_matches_the_chatbot_scenario(client) -> None:
    """기획서 5.4: S100 E.OC → 고장 탭에서 E.OC 를 강조할 수 있다."""
    detail = client.get(f"/api/products/{S100}").json()

    assert detail["tabs"] == list(TAB_ORDER)
    assert (detail["division_label"], detail["family_label"]) == (
        "자동화",
        "Variable frequency drives",
    )
    eoc = [f for f in detail["faults"] if f["error_code"] == "E.OC"]
    assert [f["section"] for f in eoc] == ["3.1", "3.2", "3.3"]
    assert eoc[0]["doc_id"] == "TG-INV-LSLV0075-S100"
    assert eoc[0]["symptom"] == "Over-current trip during acceleration"
    assert eoc[2]["needs_rma"] is True
    # 사양 행에는 근거 문서·절이 붙는다 (RAG 근거와 같은 번호)
    spec = detail["info"]["specs"][0]
    assert spec["doc_id"].startswith("DS-") and spec["section"]
    assert detail["info"]["ordering"]["warranty_months"] == "24"
    assert detail["install"]["doc_id"] == "IG-INV-LSLV0075-S100"
    assert detail["install"]["sections"][0]["section"] == "1"
    assert detail["firmware"]["latest"] == "3.10"
    assert detail["firmware"]["releases"][0]["latest"] is True  # 최신이 먼저
    assert detail["faq"]["doc_id"] == "FAQ-DRIVE"
    assert detail["faq"]["items"][0]["section"] == "Q1"
    assert {p["doc_id"] for p in detail["faq"]["policies"]} >= {"POL-WARRANTY", "POL-RETURN"}
    assert [d["doc_id"] for d in detail["docs"]][:4] == [
        "DS-INV-LSLV0075-S100",
        "IG-INV-LSLV0075-S100",
        "TG-INV-LSLV0075-S100",
        "RN-INV-LSLV0075-S100",
    ]


def test_navigation_tabs_exist_on_product_detail() -> None:
    """챗봇 화면 이동 규칙의 탭 이름 = 상세 응답의 탭 이름 (펌웨어 없는 제품의 firmware 제외)."""
    nav_tabs = {r["tab"] for r in CATALOG.tables.navigation.values()} - {"tree"}

    assert nav_tabs <= set(TAB_ORDER)
    for code in PRODUCTS:
        assert nav_tabs - {"firmware"} <= set(CATALOG.detail(code)["tabs"]), code


def test_unknown_product_is_404(client) -> None:
    assert client.get("/api/products/NOPE-1").status_code == 404


def test_long_sections_are_joined_back() -> None:
    """chunking 이 긴 절을 조각으로 나눠도 상세에는 절 하나로 나온다."""
    for code in PRODUCTS:
        for section in CATALOG.detail(code)["install"]["sections"]:
            assert section["text"].strip()
        sections = [s["section"] for s in CATALOG.detail(code)["install"]["sections"]]
        assert len(sections) == len(set(sections)), code


# 문서


def test_document_opens_with_sections(client) -> None:
    doc = client.get(f"/api/products/{S100}/docs/TG-INV-LSLV0075-S100").json()

    assert doc["doc_type"] == "TG" and doc["title"]
    section = next(s for s in doc["sections"] if s["section"] == "3.1")
    assert section["title"] == "E.OC — Over-current trip during acceleration"
    assert "acceleration" in section["text"]


def test_family_faq_and_policies_open_from_the_product(client) -> None:
    assert client.get(f"/api/products/{S100}/docs/FAQ-DRIVE").status_code == 200
    assert client.get(f"/api/products/{S100}/docs/POL-WARRANTY").status_code == 200


@pytest.mark.parametrize("doc_id", ["DS-MCCB-ABS-103c", "FAQ-PLC", "../../ref/agents.csv"])
def test_documents_of_other_products_are_404(client, doc_id) -> None:
    assert client.get(f"/api/products/{S100}/docs/{doc_id}").status_code == 404
