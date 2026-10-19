# 환경 설정 (CSA-21 · 담당 김동규 · Sprint 1)
#
# pydantic-settings 의 BaseSettings 로 Settings 클래스를 만들고, .env 와 환경변수에서 읽는다.
# get_settings() 는 lru_cache 로 한 번만 만든다. 키 목록은 저장소 루트 .env.example 과 맞춘다.
#
# 다른 사람이 새 설정이 필요하면 여기와 .env.example 에 같이 추가한다.
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    # .env.example 처럼 값이 빈 키(CHROMA_PORT= 등)는 없는 것으로 보고 기본값을 쓴다
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", env_ignore_empty=True
    )

    app_env: Literal["local", "prod"] = "local"

    # 저장소 (docker compose 안에서는 docker-compose.yml 값을 쓴다)
    database_url: str = "postgresql+psycopg://cs:cs@postgres:5432/cs"
    redis_url: str = "redis://redis:6379/0"
    chroma_host: str = "chroma"
    chroma_port: int = 8000

    # 데이터 경로
    ref_dir: Path = REPO_ROOT / "data" / "ref"  # 기준표
    raw_data_dir: Path = REPO_ROOT / "data" / "raw"  # 원천 데이터

    # LLM (기획서 9.2). live: Jev + Gemini 호출 / fake: LLM 끔
    llm_provider: Literal["live", "fake"] = "fake"
    gemini_api_key: str = ""
    gemini_model_fast: str = "gemini-3.7-flash"
    gemini_model_writer: str = "gemini-3.7-flash"  # pro 는 한 문장에 85초 (K1 초과)
    jev_api_key: str = ""
    jev_base_url: str = "https://inference.do-ai.run/v1"
    jev_model: str = ""
    jev_min_confidence: float = 0.7  # 임시값. 시험 문의로 확정 (CSA-49)

    # Langfuse (CSA-48)
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"

    # 처리 흐름
    max_verify_retries: int = 2  # 자동 점검 재작성 최대 (S-06)
    sla_at_risk_ratio: float = 0.75  # SLA 경고 기준 (CSA-40)


@lru_cache
def get_settings() -> Settings:
    return Settings()
