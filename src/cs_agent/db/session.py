# DB 연결 (CSA-24 · 담당 조수빈)
#
# 할 일
# 1. get_engine(): settings.database_url (postgresql+psycopg://…) 로 엔진 생성, 한 번만 (lru_cache).
# 2. get_sessionmaker(): 요청마다 세션. FastAPI 의존성(api/deps.py)으로 넘길 수 있게.
# 3. create_all() 은 개발용. 운영은 Alembic 마이그레이션으로 만든다.
