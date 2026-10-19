# 제품 대시보드 API (CSA-36 · CSA-37 · 담당 조수빈)
#
# router = APIRouter(prefix="/products"). 데이터는 rules/tables.py 의 products (product_master.csv).
# - GET /api/products/tree  → 대분류 3 · 중분류 11 · 소분류 23 트리
#     [{division, label, families: [{family, products: [{code, name}]}]}]
#     대분류 이름(전력·자동화·에너지)은 가정이므로 기획서 5.2 확정본으로 맞춘다.
# - GET /api/products/{code} → 제품 상세: 정보·설치·고장·펌웨어·FAQ·문서 탭 내용
#     탭 내용은 기술문서(data/raw/docs)와 기준표(사양·고장 코드·펌웨어 이력, CSA-19)에서 가져온다.
#     없는 코드는 404.
