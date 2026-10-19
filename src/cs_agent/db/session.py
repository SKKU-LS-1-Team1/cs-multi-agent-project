"""DB 연결. DATABASE_URL이 없으면 None을 돌려주고, 서비스는 메모리 저장소를 쓴다."""

from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import sessionmaker

from cs_agent.config import get_settings


@lru_cache
def get_engine() -> Engine | None:
    url = get_settings().database_url
    return create_engine(url, pool_pre_ping=True) if url else None


def get_sessionmaker() -> sessionmaker | None:
    engine = get_engine()
    return sessionmaker(engine, expire_on_commit=False) if engine else None


def create_all() -> None:
    from cs_agent.db.models import Base

    engine = get_engine()
    if engine is not None:
        Base.metadata.create_all(engine)
