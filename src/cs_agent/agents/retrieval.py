# 지식 검색 에이전트 — ④ 1차 검색 · ⑧ 근거 확정 (CSA-28 · 담당 박종석 · Sprint 1)
#
# 답변 작성(⑨)과 챗봇(CSA-32)이 함께 쓴다. ChromaDB 컬렉션 2개(기획서 7.1).
# - `docs`: 공식 문서·FAQ·정책을 절 단위로 (CSA-18에서 적재). 값·절차·정책의 근거. 값이 충돌하면
#     이쪽.
# - `cases`: 해결 사례 (train에 연결된 것만). 비슷한 문의를 어떻게 풀었는지, 문장 본보기. 참고로만.
#
# 할 일
# 1. Retriever 규약: search(query, k, where) → list[Evidence]. where 는 메타데이터 필터
#    (product_code, doc_type, family). Evidence.source 에 "docs" / "cases" 를 넣는다.
# 2. ChromaRetriever: settings.chroma_host/port 로 chromadb.HttpClient 에 붙는다 (extra: rag).
#    임베딩 모델은 적재(pipeline/embed_docs.py)와 반드시 같은 것을 쓴다.
# 3. default_retrievers(): CHROMA_HOST 가 있으면 Chroma 2개, 없으면 로컬 개발용 대체 구현
#    (data/raw/docs 를 pipeline/chunking.py 로 읽어 키워드 검색)을 돌려준다.
# 4. first_pass(): 유형이 정해지기 전에 원문으로 넓게 가져온다 (분류·추출과 병렬, N-01).
#    docs top-8 + cases top-3 정도.
# 5. finalize_evidence(): 추출된 제품으로 거르고, 유형별로 문서 종류 가중치(사양→DS, 설치→IG,
#    불량→TG, 펌웨어→RN …)를 줘서 재정렬한다. docs 3개 + cases 2개 정도.
# 6. 사양값·보증기간·에러코드처럼 정확히 맞아야 하는 값은 벡터 검색이 아니라 기준표 조회로 한다
#    (CSA-19). 에러코드가 있으면 고장 카탈로그 정확 조회, 없으면 증상으로 사례 검색.
#
# 완료 기준
# - valid: 근거 일치율 K3 (reference_doc_id + reference_section 이 top-3 안) 측정·보고
# - test 티켓에 연결된 사례가 cases 컬렉션에 없음
#
# 참고: 기획서 v10 7.1, 에이전트_구조_제안.md 6장
#
# 만들 것 (이름·모양은 다른 파일이 이대로 부른다)
#
#   class Retriever(Protocol):
#       def search(
#           self, query: str, k: int = 5, where: dict[str, str] | None = None
#       ) -> list[Evidence]: ...
#
#   def default_retrievers() -> tuple[Retriever, Retriever]:
#       """(docs, cases) 검색기. 위 '할 일 3' 참고."""
#
#   def first_pass(docs: Retriever, cases: Retriever, text: str, k: int = 8) -> list[Evidence]:
#       """④ 원문 기반 1차 검색."""
#
#   def finalize_evidence(
#       candidates: list[Evidence], extraction: Extraction, k: int = 3
#   ) -> list[Evidence]:
#       """⑧ 제품·유형으로 거르고 재정렬한 확정 근거."""
