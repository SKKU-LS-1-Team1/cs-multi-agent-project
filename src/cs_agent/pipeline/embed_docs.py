# 임베딩 → PostgreSQL(pgvector) 적재 (CSA-18 · 담당 박종석 · Sprint 1)
# 실행 예: uv run --extra rag --extra llm python -m cs_agent.pipeline.embed_docs
#
# 결정 (팀장 확정)
# - 벡터 저장소: ChromaDB 대신 PostgreSQL + pgvector. 테이블은 db/models.py (CSA-24) 의
#   doc_chunks, resolution_cases.embedding.
# - 임베딩 모델: settings.embedding_model = gemini-embedding-2, settings.embedding_dim = 1536.
#   15개 언어 문의로 영어 문서를 찾는 다국어 모델. 한·영 같은 뜻 유사도 0.75, 다른 뜻 0.44 확인.
#   기본 3072차원은 pgvector HNSW 인덱스 한도(2000)를 넘어서 output_dimensionality=1536 으로 받는다.
#
# 할 일
# 1. embed(texts, task_type) → list[list[float]]: google-genai (extra: llm) 로 부른다.
#      client.models.embed_content(model=settings.embedding_model, contents=text,
#          config=EmbedContentConfig(task_type=..., output_dimensionality=settings.embedding_dim))
#    ⚠️ gemini-embedding-2 는 contents 에 글 여러 개를 목록으로 넣으면 하나로 합쳐 벡터 1개만
#    돌려준다. 글 하나당 한 번씩 부른다 (약 0.5초/건 → 1,500건 ≈ 12분, 분당 호출 제한 주의).
#    적재 = task_type "RETRIEVAL_DOCUMENT", 검색(agents/retrieval.py) = "RETRIEVAL_QUERY".
# 2. docs: pipeline/chunking.py 결과(약 900조각)를 doc_chunks 에 upsert.
#    id = "doc_id#section", text = 제목 + 본문,
#    doc_id·section·doc_type·product_code·family 열(검색 필터용).
# 3. cases: data/processed/cases_seed.parquet (CSA-17 결과, train 연결 568건)을 resolution_cases 에
#    upsert. 임베딩할 글 = 문의 요약 + 원인 + 조치 + 최종 답변. data_split = "train".
# 4. 문서가 개정되면 다시 돌려도 되도록 upsert 로 (중복 없음). 글이 안 바뀐 행은 임베딩을 다시
#    부르지 않는다 (text 해시 비교) — 비용·시간 절약.
