# FastAPI + LangGraph 백엔드 (CSA-44)
FROM python:3.11-slim

COPY --from=ghcr.io/astral-sh/uv:0.8 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --all-extras --no-dev --no-install-project

COPY alembic.ini ./
COPY src ./src
COPY data/ref ./data/ref
RUN uv sync --locked --all-extras --no-dev

EXPOSE 8000
# 시작할 때마다 DB 마이그레이션을 최신으로 맞춘 뒤 서버를 띄운다 (CSA-24). 이미 최신이면 바로 넘어간다.
# 마이그레이션이 실패하면 서버를 띄우지 않는다 (양식이 안 맞는 DB 로 돌지 않게).
CMD ["sh", "-c", "uv run --no-sync alembic upgrade head && exec uv run --no-sync uvicorn cs_agent.main:app --host 0.0.0.0 --port 8000"]
