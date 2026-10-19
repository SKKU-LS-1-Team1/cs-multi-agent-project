# 기술문서 절 단위 나누기 (CSA-18 · 담당 박종석 · Sprint 1)
#
# 입력: data/raw/docs/**/*.md (제품 23개 × DS·IG·TG·RN/MG + FAQ 5개, doc_index.csv 참고)
# 각 문서 앞에 front matter(--- doc_id, doc_type, product_code, family, revision, language ---)가
#   있다.
#
# 할 일
# 1. parse_front_matter(raw) → (메타데이터 dict, 본문)
# 2. chunk_markdown(raw) → Chunk 목록. "## 2. ..." / "### 2.1 ..." 제목마다 자르고 절
#      번호("2.1")를 section 에 넣는다.
#    첫 ## 제목 앞(문서 제목, "SYNTHETIC DATA" 안내문)은 버린다.
#    Chunk = doc_id, section, title, text, metadata
# 3. iter_doc_chunks(docs_dir) → 폴더 전체
# 절 단위여야 tickets 의 reference_section 정답과 비교할 수 있다 (K3).
# 표(| 항목 | 값 |)가 잘리지 않게 한다. 너무 긴 절은 나누되 section 은 유지.
