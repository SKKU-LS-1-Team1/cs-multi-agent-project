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


def run_migrations_offline() -> None:
    context.configure(url=URL, target_metadata=Base.metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(URL)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=Base.metadata)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
