# DB 연결 (CSA-24 · 담당 김동규)
#
# - get_engine(): settings.database_url (postgresql+psycopg://…) 로 엔진을 한 번만 만든다.
# - get_sessionmaker(): 세션 공장. 요청·작업 단위로 `with get_sessionmaker()() as s:` 또는
#   `with get_sessionmaker().begin() as s:` (끝나면 커밋) 로 쓴다.
# - upgrade(): Alembic 마이그레이션을 최신으로. 운영·개발 모두 테이블은 이걸로 만든다
#   (Base.metadata.create_all 은 쓰지 않는다: 마이그레이션 기록과 실제 DB 가 어긋난다).
#
# 명령으로 하려면 (저장소 루트):
#   uv run alembic upgrade head                       # 최신으로
#   uv run alembic revision --autogenerate -m "설명"  # models.py 를 바꾼 뒤 리비전 만들기
#   docker compose exec api uv run --no-sync alembic upgrade head   # 서버 컨테이너 안에서
from functools import lru_cache
from pathlib import Path

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from cs_agent.config import get_settings

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


@lru_cache
def get_engine(url: str | None = None) -> Engine:
    return create_engine(url or get_settings().database_url, pool_pre_ping=True)


@lru_cache
def get_sessionmaker(url: str | None = None) -> sessionmaker[Session]:
    return sessionmaker(get_engine(url), expire_on_commit=False)


def alembic_config(url: str | None = None):
    from alembic.config import Config

    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    config.set_main_option(
        "sqlalchemy.url", (url or get_settings().database_url).replace("%", "%%")
    )
    return config


def upgrade(url: str | None = None, revision: str = "head") -> None:
    from alembic import command

    command.upgrade(alembic_config(url), revision)
