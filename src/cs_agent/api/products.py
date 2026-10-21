# 제품 대시보드 API (CSA-60 · 담당 김동규. 화면은 CSA-36 · CSA-37 · 조수빈)
#
# main.py 에서 "/api" 아래 등록. 내용은 services/catalog.py 가 기준표·기술문서에서 모은다.
# - GET /api/products/tree  → 대분류 3 · 중분류 11 · 소분류 23 트리
#     [{division, label, families: [{family, label, products: [{code, name}]}]}]
#     대분류 이름(전력·자동화·에너지)은 family_divisions.csv. 기획서 5.2 확정본으로 맞춘다.
# - GET /api/products/{code} → 제품 상세: tabs(내용 있는 탭만) + info · install · faults ·
#     firmware · faq · docs 탭 내용. 없는 코드는 404. 응답 모양은 services/catalog.py 맨 위 참고.
# - GET /api/products/{code}/docs/{doc_id} → 문서 자료실의 문서 하나 (절 목록). 그 제품의 docs 탭에
#     없는 문서는 404.
from typing import Any

from fastapi import APIRouter, HTTPException

from cs_agent.services.catalog import get_catalog

router = APIRouter(prefix="/products", tags=["products"])


@router.get("/tree")
def product_tree() -> list[dict[str, Any]]:
    return get_catalog().tree()


@router.get("/{code}")
def product_detail(code: str) -> dict[str, Any]:
    detail = get_catalog().detail(code)
    if detail is None:
        raise HTTPException(404, f"unknown product: {code}")
    return detail


@router.get("/{code}/docs/{doc_id}")
def product_document(code: str, doc_id: str) -> dict[str, Any]:
    document = get_catalog().document(code, doc_id)
    if document is None:
        raise HTTPException(404, f"document {doc_id} is not available for {code}")
    return document
