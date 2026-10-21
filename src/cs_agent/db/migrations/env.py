# Alembic 실행 환경 (CSA-24). 비교 대상은 db/models.py 의 Base.metadata.
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine

from cs_agent.config import get_settings
from cs_agent.db.models import Base

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)

URL = config.get_main_option("sqlalchemy.url") or get_settings().database_url

# 그래프 체크포인트 테이블은 PostgresSaver.setup() 이 따로 만든다 (graph/builder.py).
# autogenerate 가 이 테이블을 지우는 리비전을 만들지 않도록 비교에서 뺀다.
CHECKPOINT_TABLES = {
    "checkpoints",
    "checkpoint_blobs",
    "checkpoint_writes",
    "checkpoint_migrations",
}


def include_name(name, type_, parent_names) -> bool:
    return not (type_ == "table" and name in CHECKPOINT_TABLES)


def run_migrations_offline() -> None:
    context.configure(
        url=URL, target_metadata=Base.metadata, literal_binds=True, include_name=include_name
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(URL)
    with engine.connect() as connection:
        context.configure(
            connection=connection, target_metadata=Base.metadata, include_name=include_name
        )
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
