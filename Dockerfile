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
CMD ["uv", "run", "--no-sync", "uvicorn", "cs_agent.main:app", "--host", "0.0.0.0", "--port", "8000"]
