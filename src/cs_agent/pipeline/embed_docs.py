# 임베딩 → ChromaDB 적재 (CSA-18 · 담당 박종석 · Sprint 1)
# 실행 예: uv run --extra rag python -m cs_agent.pipeline.embed_docs
#
# 할 일
# 1. 임베딩 모델 결정: 15개 언어 문의로 영어 문서를 찾아야 하므로 다국어 모델. 결정 근거를 여기
#      적는다.
# 2. `docs` 컬렉션: pipeline/chunking.py 결과를 upsert.
#    id = "doc_id#section", document = 제목 + 본문,
#    metadata = doc_id, section, doc_type, product_code, family (검색 필터에 쓴다)
# 3. `cases` 컬렉션: data/processed/cases_seed.parquet (CSA-17 결과, train 연결 사례만)
#    document = 문의 요약 + 원인 + 조치 + 최종 답변, metadata = case_id, category, product_code,
#      error_code
# 4. 접속: settings.chroma_host 가 있으면 HttpClient, 없으면 data/chroma 에 PersistentClient.
# 5. 문서가 개정되면 다시 돌려도 되도록 upsert 로 (중복 없음).
