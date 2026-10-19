"""제품 대시보드 API (CSA-36 분류 트리 · CSA-37 제품 상세)."""

from collections import defaultdict

from fastapi import APIRouter, HTTPException

from cs_agent.rules.tables import load_tables

router = APIRouter(prefix="/products", tags=["products"])

# 대분류 이름. TODO(CSA-36): 기획서 5.2 분류 트리 확정본으로 맞춘다.
DIVISION_LABELS = {"POWER": "전력", "AUTOMATION": "자동화", "ENERGY": "에너지"}


@router.get("/tree")
def tree() -> list[dict]:
    """대분류 3 · 중분류 11 · 소분류 23."""
    grouped: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for p in load_tables().products.values():
        grouped[p.division][p.family].append({"code": p.code, "name": p.name})
    return [
        {
            "division": division,
            "label": DIVISION_LABELS.get(division, division),
            "families": [{"family": f, "products": ps} for f, ps in families.items()],
        }
        for division, families in grouped.items()
    ]


@router.get("/{code}")
def detail(code: str) -> dict:
    """제품 상세 탭: 정보 · 설치 · 고장 · 펌웨어 · FAQ · 문서. TODO(CSA-37): 탭별 내용 조회."""
    product = load_tables().products.get(code)
    if product is None:
        raise HTTPException(404, "product not found")
    return {
        "code": product.code,
        "name": product.name,
        "family": product.family,
        "tabs": ["info", "install", "faults", "firmware", "faq", "docs"],
    }
