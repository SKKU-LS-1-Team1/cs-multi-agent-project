"""환경 설정. 값은 `.env` 또는 환경변수에서 읽는다 (CSA-21)."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "local"

    # 저장소. 비워 두면 메모리 구현을 쓴다 (테스트·로컬 시연).
    database_url: str | None = None  # postgresql+psycopg://cs:cs@postgres:5432/cs
    redis_url: str | None = None  # redis://redis:6379/0
    chroma_host: str | None = None  # chromadb
    chroma_port: int = 8000

    # 기준표(규칙표·SLA·제품 기준정보) 폴더 (CSA-19)
    ref_dir: Path = REPO_ROOT / "data" / "ref"
    # 원천 데이터 폴더 (CS_AI_Agent_Training_Data_v1, git에 올리지 않음)
    raw_data_dir: Path = REPO_ROOT / "data" / "raw"

    # LLM (기획서 9.2: 판단은 Jev, 작성은 Gemini). "fake"면 외부 호출 없이 동작한다.
    llm_provider: str = "fake"  # fake | live
    gemini_api_key: str | None = None
    gemini_model_fast: str = "gemini-2.5-flash"
    gemini_model_writer: str = "gemini-2.5-pro"
    jev_api_key: str | None = None
    jev_base_url: str = "https://inference.do-ai.run/v1"
    jev_model: str = "jev"
    jev_min_confidence: float = 0.7  # 시험 문의로 확정 (CSA-35·CSA-49)

    # Langfuse (CSA-48)
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    langfuse_host: str = "https://cloud.langfuse.com"

    # 처리 흐름
    max_verify_retries: int = 2  # 자동 점검 재작성 최대 횟수 (S-06)
    sla_at_risk_ratio: float = 0.75  # 75% 경고 (CSA-40)


@lru_cache
def get_settings() -> Settings:
    return Settings()
