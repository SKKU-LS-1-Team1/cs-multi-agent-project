# 환경 설정 (CSA-21 · 담당 김동규 · Sprint 1)
#
# pydantic-settings 의 BaseSettings 로 Settings 클래스를 만들고, .env 와 환경변수에서 읽는다.
# get_settings() 는 lru_cache 로 한 번만 만든다. 키 목록은 저장소 루트 .env.example 과 맞춘다.
#
# 넣을 설정
# - app_env: local | prod
# - 저장소: database_url (postgresql+psycopg://cs:cs@postgres:5432/cs), redis_url, chroma_host,
#     chroma_port
# - 데이터 경로: ref_dir = 저장소/data/ref (기준표), raw_data_dir = 저장소/data/raw (원천 데이터,
#     git 제외)
# - LLM (기획서 9.2): llm_provider (live | fake), gemini_api_key, gemini_model_fast,
#     gemini_model_writer,
#   jev_api_key, jev_base_url (https://inference.do-ai.run/v1), jev_model,
#   jev_min_confidence (Jev 확신도 기준, 시험 문의로 확정 CSA-49)
# - Langfuse (CSA-48): langfuse_public_key, langfuse_secret_key, langfuse_host
# - 처리 흐름: max_verify_retries = 2 (자동 점검 재작성 최대, S-06), sla_at_risk_ratio = 0.75
#     (CSA-40)
#
# 다른 사람이 새 설정이 필요하면 여기와 .env.example 에 같이 추가한다.
